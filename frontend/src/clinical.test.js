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
