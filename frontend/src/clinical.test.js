import { describe, expect, it } from "vitest";
import { criterionIds, criteriaLabels } from "./clinical";

describe("clinical presentation schema", () => {
  it("contains exactly nine inattention and nine hyperactivity/impulsivity criteria", () => {
    expect(criterionIds.filter(id => id.startsWith("A1.")).length).toBe(9);
    expect(criterionIds.filter(id => id.startsWith("A2.")).length).toBe(9);
    expect(new Set(Object.values(criteriaLabels)).size).toBe(18);
  });
});

