import { describe, expect, it } from "vitest";
import { criteriaGroups, criterionIds, criteriaLabels, criterionOutcomeLabels } from "./clinical";

describe("clinical presentation schema", () => {
  it("contains exactly nine inattention and nine hyperactivity/impulsivity criteria", () => {
    expect(criterionIds.filter(id => id.startsWith("A1.")).length).toBe(9);
    expect(criterionIds.filter(id => id.startsWith("A2.")).length).toBe(9);
    expect(new Set(Object.values(criteriaLabels)).size).toBe(18);
  });

  it("provides report-table groups and explicit clinician outcomes", () => {
    expect(criteriaGroups.map(group => group.prefix)).toEqual(["A1.", "A2."]);
    expect(criterionOutcomeLabels).toEqual({
      met: "Met",
      not_met: "Not met",
      insufficient: "Insufficient evidence",
      unreviewed: "Not reviewed",
    });
  });
});

import {outcomeColumns, reviewedCriteria, reportCriteria} from './clinical';

it('adult review requires both periods, adolescent review uses one', () => {
  const criteria=[{clinician_outcome:'met',adulthood_outcome:'met',childhood_outcome:'unreviewed'}];
  expect(reviewedCriteria(criteria,'adult')).toBe(0);
  expect(reviewedCriteria(criteria,'adolescent')).toBe(1);
  expect(outcomeColumns('adult').map(([,label])=>label)).toEqual(['Adulthood','Childhood']);
  expect(outcomeColumns('adolescent')).toEqual([['clinician_outcome','Clinician outcome']]);
});

it('report tables use the saved draft decisions', () => {
  const saved=[{criterion_id:'A1.1',adulthood_outcome:'not_met'}];
  const actual=reportCriteria({input_snapshot:{criteria:saved,case:{cohort:'adult'}}},{criteria:[{adulthood_outcome:'met'}],case:{cohort:'adolescent'}});
  expect(actual).toEqual({criteria:saved,cohort:'adult'});
});
