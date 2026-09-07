from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.ai import BedrockClinicalAI, LocalHeuristicAI
from app.clinical import DraftResult, DraftSection, CRITERIA, REPORT_SECTIONS
from app.drafting import DIVA_SECTIONS, GENERAL_DRAFT_GROUPS, validate_draft
from app.db import get_db, init_db
from app.worker import process_draft, _generate_files


@pytest.fixture
def feedback():
    return json.loads((Path(__file__).parent / 'fixtures/report_feedback.json').read_text())


def validate(feedback, sections):
    return validate_draft(DraftResult.model_validate({'sections':sections}), feedback['case'], feedback['evidence'], feedback['instruments'])


def section(result, key):
    return next(s for s in result.sections if s.key == key)


def test_all_criteria_order_quotes_and_negative_accounts(feedback):
    result = validate(feedback, feedback['diva_sections'][::-1])
    for key, prefix in [('inattention', 'A1.'), ('hyperactivity_impulsivity', 'A2.')]:
        paragraphs = section(result, key).paragraphs
        assert [p.criterion_id for p in paragraphs] == [f'{prefix}{i}' for i in range(1,10)]
        assert all(p.kind == 'narrative' and len(p.quotations) == 2 for p in paragraphs)
    assert 'I stay seated when I need to.' in section(result,'hyperactivity_impulsivity').paragraphs[1].text
    assert 'In contrast' in section(result, 'inattention').paragraphs[0].text


@pytest.mark.parametrize('change,reason', [
    ({'evidence_ids':['questionnaire-in-mixed-source']}, 'non-DIVA'),
    ({'instrument_ids':['self-scale']}, 'non-DIVA'),
    ({'criterion_id':'A1.2'}, 'incorrect criterion'),
    ({'evidence_ids':['foreign-case-id']}, 'invalid evidence'),
    ({'text':'The client reported “invented quote”.'}, 'unsupported quotations'),
    ({'text':"The client reported 'invented quote'."}, 'unsupported quotations'),
])
def test_diva_validation_fails_closed(feedback, change, reason):
    paragraph = deepcopy(feedback['diva_sections'][0]['paragraphs'][0]);paragraph.update(change)
    result = validate(feedback,[{'key':'inattention','heading':'ignored','paragraphs':[paragraph]}])
    assert all(p.kind == 'missing_information' for p in section(result,'inattention').paragraphs)
    assert any(reason in warning for warning in result.validation_warnings)


def test_missing_evidence_never_means_not_met(feedback):
    feedback['evidence'] = [e for e in feedback['evidence'] if e.get('assessment_type') != 'diva']
    result = validate(feedback, [])
    assert len(section(result,'inattention').paragraphs) == 9
    assert all('No verified DIVA account' in p.text for p in section(result,'inattention').paragraphs)
    assert not any('Not met' in p.text for s in result.sections for p in s.paragraphs)


def test_instrument_only_comparison_supported_cognitive_separated(feedback):
    text = ('The clinician interpreted the client and teacher responses as describing similar attention concerns, '
            'while the parent reported fewer difficulties. The teacher used a different scale, so its numbers are not directly comparable.')
    result=validate(feedback,[{'key':'instruments','heading':'Questionnaires','paragraphs':[
        {'text':text,'instrument_ids':['self-scale','parent-scale','teacher-scale']},
        {'text':'Cognitive results do not belong here.','instrument_ids':['cognitive-result']},
        {'text':'Unverified result.','instrument_ids':['unverified']},
    ]}])
    assert [p.text for p in section(result,'instruments').paragraphs] == [text]


def test_summary_and_demographics_are_application_owned(feedback):
    conclusion=feedback['case']['final_diagnostic_conclusion']
    result=validate(feedback,[{'key':'summary','heading':'Summary','paragraphs':[
        {'text':conclusion},{'text':conclusion,'evidence_ids':['family']},
        {'text':'In the clinician’s interpretation, further childhood information would help clarify the outcome.','evidence_ids':['diva-child-A1.1']}
    ]}])
    summary=section(result,'summary').paragraphs
    assert sum(p.text==conclusion for p in summary)==1
    assert summary[0].kind=='clinician_conclusion'
    assert summary[-1].text.startswith('In the clinician’s interpretation')
    opening=section(result,'background').paragraphs[0]
    assert opening.kind=='intake'
    assert opening.text.index('28')<opening.text.index('female')<opening.text.index('Melbourne')<opening.text.index('partner')
    feedback['case']['demographics']={'pronouns':'she/her'}
    feedback['case']['final_diagnostic_conclusion']=''
    result=validate(feedback,[])
    assert not section(result,'background').paragraphs
    assert section(result,'summary').paragraphs[0].text=="The clinician's diagnostic impression is pending."


def test_recommendation_groups_require_relevant_support(feedback):
    paragraphs=[
        {'text':'For clinician review, use drawing to design a visual checklist.','evidence_ids':['strength'],'recommendation_group':'strengths','recommendation_basis':'practical'},
        {'text':'For clinician review, discuss available care options.','evidence_ids':['referral'],'recommendation_group':'general','recommendation_basis':'guideline','guideline_ids':['aadpa-3.1']},
        {'text':'Unsupported cognitive recommendation.','evidence_ids':['family'],'recommendation_group':'cognitive','recommendation_basis':'practical'},
        {'text':'Invented guideline.','evidence_ids':['family'],'recommendation_group':'general','recommendation_basis':'guideline','guideline_ids':['made-up']},
    ]
    result=validate(feedback,[{'key':'recommendations','heading':'Recommendations','paragraphs':paragraphs}])
    assert [p.recommendation_group for p in section(result,'recommendations').paragraphs]==['general','strengths']


def test_general_draft_groups_cover_every_modelled_section():
    grouped=[key for _,keys in GENERAL_DRAFT_GROUPS for key in keys]
    modelled={key for key,_ in REPORT_SECTIONS} - DIVA_SECTIONS - {'diagnostic_criteria'}
    assert set(grouped)==modelled
    assert len(grouped)==len(set(grouped)), 'a section may only be drafted by one group'
    assert GENERAL_DRAFT_GROUPS[-1][0]=='synthesis', 'the summary must be drafted last'


def test_separate_model_call_cannot_access_questionnaires(feedback, monkeypatch):
    calls={}
    def fake_json(self, operation, system, prompt):
        calls[operation]=json.loads(prompt)
        if operation=='draft_diva':
            return {'sections':feedback['diva_sections']}
        return {'sections':[{'key':'inattention','heading':'Injected','paragraphs':[{'text':'QUESTIONNAIRE_ONLY_SENTINEL','evidence_ids':['questionnaire-in-mixed-source']}]}]}
    monkeypatch.setattr(BedrockClinicalAI,'_json',fake_json)
    provider=object.__new__(BedrockClinicalAI)
    result=provider.draft(feedback['case'],feedback['evidence'],feedback['criteria'],feedback['instruments'])
    diva=calls['draft_diva']
    assert 'QUESTIONNAIRE_ONLY_SENTINEL' not in json.dumps(diva)
    assert set(k for k,_ in diva['required_sections'])==DIVA_SECTIONS
    assert 'clinician_criteria' not in diva and 'case' not in diva
    assert len(section(result,'inattention').paragraphs)==9
    assert all('QUESTIONNAIRE_ONLY_SENTINEL' not in p.text for p in section(result,'inattention').paragraphs)
    assert 'guideline_references' in calls['draft_synthesis']


def test_each_draft_call_is_bounded_to_its_own_sections(feedback, monkeypatch):
    calls={}
    def fake_json(self, operation, system, prompt):
        calls[operation]=json.loads(prompt)
        return {'sections':[]}
    monkeypatch.setattr(BedrockClinicalAI,'_json',fake_json)
    provider=object.__new__(BedrockClinicalAI)
    result=provider.draft(feedback['case'],feedback['evidence'],feedback['criteria'],feedback['instruments'])
    # No single request may be asked for every section at once; that is what exhausted
    # the output budget and failed the whole draft.
    for operation,payload in calls.items():
        requested={k for k,_ in payload['required_sections']}
        assert len(requested)<=3, f'{operation} requests too many sections at once'
    for label,keys in GENERAL_DRAFT_GROUPS:
        if f'draft_{label}' in calls:
            assert {k for k,_ in calls[f'draft_{label}']['required_sections']}==set(keys)
    # The findings call only ever receives instrument-backed provenance.
    findings=calls.get('draft_findings')
    if findings:
        assert all(e['assessment_type'] in {'questionnaire','cognitive'} for e in findings['verified_evidence'])
    # Every section still reaches the finished report even though no group produced text.
    assert [s.key for s in result.sections]==[key for key,_ in REPORT_SECTIONS]


def test_local_organiser_has_no_eight_item_limit_or_mixed_source_leakage(feedback):
    result=LocalHeuristicAI().draft(feedback['case'],feedback['evidence'],feedback['criteria'],feedback['instruments'])
    for key in ['inattention','hyperactivity_impulsivity']:
        paragraphs=section(result,key).paragraphs
        assert {p.criterion_id for p in paragraphs}=={c for c in CRITERIA if c.startswith('A1' if key=='inattention' else 'A2')}
        assert all('QUESTIONNAIRE_ONLY_SENTINEL' not in p.text for p in paragraphs)
    assert result.validation_warnings[-1].startswith('The local organiser')


def test_additive_migration_keeps_legacy_outcomes(app, authenticated):
    client,headers=authenticated
    case=client.post('/api/cases',headers=headers,json={'cohort':'adult','patient_initials':'SYN'}).json
    with app.app_context():
        db=get_db()
        db.execute("UPDATE criterion_assessments SET clinician_outcome='met' WHERE case_id=?",(case['id'],))
        db.execute('ALTER TABLE criterion_assessments DROP COLUMN adulthood_outcome')
        db.execute('ALTER TABLE criterion_assessments DROP COLUMN childhood_outcome')
        db.commit()
        init_db();init_db()
        rows=db.execute('SELECT * FROM criterion_assessments WHERE case_id=?',(case['id'],)).fetchall()
        assert all(r['clinician_outcome']=='met' and r['adulthood_outcome']=='unreviewed' and r['childhood_outcome']=='unreviewed' for r in rows)


@pytest.mark.parametrize('cohort,fields',[('adult',['adulthood_outcome','childhood_outcome']),('adolescent',['clinician_outcome'])])
def test_age_period_api_and_snapshot_approval(app,authenticated,cohort,fields,monkeypatch):
    from app.worker import process_extract
    import io
    client,headers=authenticated
    case=client.post('/api/cases',headers=headers,json={'cohort':cohort,'patient_initials':'SYN','cloud_consent':True,'final_diagnostic_conclusion':'Ignored on create'}).json
    cid=case['id']
    client.patch(f'/api/cases/{cid}',headers=headers,json={'final_diagnostic_conclusion':'The clinician has not established an ADHD diagnosis.'})
    source=client.post(f'/api/cases/{cid}/sources',headers=headers,data={'file':(io.BytesIO(b'The client reported difficulty finishing work tasks.'),'test.txt'),'assessment_type':'diva','instrument':'DIVA-5'}).json
    with app.app_context():process_extract({'source_id':source['source_id']},cid)
    detail=client.get(f'/api/cases/{cid}').json
    evidence=detail['evidence'][0]
    response=client.patch(f'/api/cases/{cid}/evidence/{evidence["id"]}',headers=headers,json={'assessment_type':'diva','criterion_ids':['A1.4'],'timeframe':'adulthood' if cohort=='adult' else 'adolescence','verified':True})
    assert response.status_code==200
    assert response.json['criterion_ids']==['A1.4']
    for criterion in detail['criteria']:
        for field in fields:
            response=client.put(f'/api/cases/{cid}/criteria/{criterion["criterion_id"]}',headers=headers,json={field:'insufficient'})
            assert response.status_code==200
    with app.app_context():process_draft({},cid)
    draft=client.get(f'/api/cases/{cid}').json['drafts'][0]
    assert draft['input_snapshot']['criteria'][0][fields[0]]=='insufficient'
    client.patch(f'/api/cases/{cid}/drafts/{draft["id"]}',headers=headers,json={'state':'review-ready','warnings_acknowledged':True})
    approved=client.post(f'/api/cases/{cid}/drafts/{draft["id"]}/approve',headers=headers,json={})
    assert approved.status_code==200,approved.json
    with app.app_context():_generate_files(draft['id'])
    original=client.get(f'/api/cases/{cid}/drafts/{draft["id"]}/docx').data
    client.put(f'/api/cases/{cid}/criteria/A1.1',headers=headers,json={fields[0]:'met'})
    with app.app_context():_generate_files(draft['id'])
    assert client.get(f'/api/cases/{cid}/drafts/{draft["id"]}/docx').data==original
    assert client.post(f'/api/cases/{cid}/drafts/{draft["id"]}/approve',headers=headers,json={}).status_code==409


def test_instrument_update_and_source_classification(authenticated):
    import io
    client, headers = authenticated
    case = client.post('/api/cases', headers=headers, json={'cohort':'adult','patient_initials':'SYN'}).json
    cid = case['id']
    source = client.post(f'/api/cases/{cid}/sources', headers=headers,
                        data={'file':(io.BytesIO(b'Synthetic DIVA interview text.'),'test.txt'),'assessment_type':'diva','instrument':'DIVA-5'}).json
    response = client.patch(f'/api/cases/{cid}/sources/{source["source_id"]}',headers=headers,
                            json={'assessment_type':'other','instrument':'Mixed assessment'})
    assert response.status_code == 200
    assert response.json['original_filename']=='test.txt' and response.json['instrument']=='Mixed assessment'
    created = client.post(f'/api/cases/{cid}/instruments',headers=headers,json={
        'instrument':'Synthetic profile','assessment_type':'questionnaire','respondent':'parent','scores':{'attention':52},
        'interpretation':'The parent reported fewer attention concerns.','verified':True,
    })
    assert created.status_code==201
    iid=created.json['id']
    changed=client.patch(f'/api/cases/{cid}/instruments/{iid}',headers=headers,json={'assessment_type':'cognitive'})
    assert changed.status_code==200 and changed.json['verified'] is False
    verified=client.patch(f'/api/cases/{cid}/instruments/{iid}',headers=headers,json={'assessment_type':'questionnaire','verified':True})
    assert verified.json['verified'] is True and verified.json['scores']=={'attention':52}
    assert client.patch(f'/api/cases/{cid}/instruments/{iid}',headers=headers,json={'scores':[]}).status_code==400
