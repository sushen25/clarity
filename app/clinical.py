from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


DOMAIN_DEFINITIONS = {
    "referral": "Reason for referral, presenting concerns, goals, or questions for assessment.",
    "strengths": "Strengths, interests, capabilities, protective factors, or helpful supports.",
    "developmental": "Pregnancy, birth, milestones, childhood development, and early symptom history.",
    "medical": "Physical health, medication, sleep, sensory issues, neurological history, or medical assessment.",
    "mental_health": "Mood, anxiety, trauma, emotional wellbeing, risk, or previous mental-health care.",
    "family_social": "Family relationships, friendships, social functioning, living situation, or family history.",
    "education_work": "Educational or occupational history, performance, attendance, and task demands.",
    "inattention": "ADHD inattention symptoms such as distractibility, forgetfulness, disorganisation, or poor sustained attention.",
    "hyperactivity_impulsivity": "ADHD hyperactivity or impulsivity symptoms such as restlessness, interrupting, excessive talking, or difficulty waiting.",
    "impairment": "Functional impact or clinically significant difficulty across home, school, work, relationships, or daily living.",
    "observations": "Clinician's direct behavioural or mental-state observations during assessment.",
    "differential": "Alternative explanations, co-occurring conditions, diagnostic uncertainty, or evidence against ADHD.",
    "instrument": "Authorised rating-scale, interview, cognitive-test, or other assessment result and its interpretation.",
    "recommendation": "A recommendation, intervention, accommodation, referral, or proposed next step.",
    "other": "Relevant clinical evidence that genuinely does not fit any more specific domain.",
}
DOMAINS = tuple(DOMAIN_DEFINITIONS)
SETTINGS = ("home", "school", "work", "social", "clinical", "other", "unspecified")
CRITERIA = [f"A1.{i}" for i in range(1, 10)] + [f"A2.{i}" for i in range(1, 10)]
OUTCOMES = ("unreviewed", "met", "not_met", "insufficient")


class ExtractedEvidence(BaseModel):
    domain: Literal[*DOMAINS]
    source_location: str
    supporting_text: str = Field(min_length=1, max_length=800)
    reporter: str = ""
    setting: str = "unspecified"
    confidence: float = Field(ge=0, le=1)
    contradiction_status: Literal["none", "possible", "confirmed"] = "none"

    @field_validator("setting")
    @classmethod
    def valid_setting(cls, value: str):
        return value if value in SETTINGS else "unspecified"


class ExtractionResult(BaseModel):
    evidence: list[ExtractedEvidence] = Field(default_factory=list, max_length=250)


class DraftParagraph(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    evidence_ids: list[str] = Field(default_factory=list)


class DraftSection(BaseModel):
    key: str
    heading: str
    paragraphs: list[DraftParagraph] = Field(default_factory=list)


class DraftResult(BaseModel):
    sections: list[DraftSection]
    validation_warnings: list[str] = Field(default_factory=list, exclude=True)


REPORT_SECTIONS = [
    ("referral", "Reason for Referral / Main Concerns"),
    ("background", "Background Information"),
    ("adhd_assessment", "Attention Deficit Hyperactivity Disorder Assessment"),
    ("inattention", "Symptoms of Inattention"),
    ("hyperactivity_impulsivity", "Symptoms of Hyperactivity / Impulsivity"),
    ("observations", "Behavioural Observations"),
    ("instruments", "Assessment Instruments"),
    ("cognitive", "Cognitive Assessment"),
    ("diagnostic_criteria", "Diagnostic Criteria"),
    ("summary", "Summary and Diagnostic Conclusion"),
    ("recommendations", "Recommendations"),
]


def clinical_gaps(case: dict, evidence: list[dict], sources: list[dict]) -> list[str]:
    warnings: list[str] = []
    domains = {item["domain"] for item in evidence if item.get("verified")}
    settings = {item["setting"] for item in evidence if item.get("verified") and item.get("setting") != "unspecified"}
    reporters = {item["reporter"].strip().lower() for item in evidence if item.get("verified") and item.get("reporter")}
    required = {
        "developmental": "Developmental history has not been verified.",
        "medical": "Medical history or assessment has not been verified.",
        "mental_health": "Mental-health history has not been verified.",
        "impairment": "Clinically significant functional impairment has not been verified.",
        "differential": "Differential or co-occurring conditions have not been addressed.",
        "strengths": "The person's strengths and protective factors have not been documented.",
    }
    for domain, message in required.items():
        if domain not in domains:
            warnings.append(message)
    if len(settings) < 2:
        warnings.append("Verified evidence does not yet cover two important settings.")
    collateral_words = ("parent", "mother", "father", "carer", "guardian", "teacher", "school")
    if case["cohort"] == "adolescent" and not any(word in reporter for reporter in reporters for word in collateral_words):
        warnings.append("No verified parent/carer or teacher collateral evidence is present.")
    if not sources:
        warnings.append("No source documents have been uploaded.")
    if not case.get("cloud_consent"):
        warnings.append("Australian cloud-processing consent has not been acknowledged.")
    return warnings
