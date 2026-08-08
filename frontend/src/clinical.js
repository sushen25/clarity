export const criteriaLabels = {
  "A1.1": "Careless mistakes / attention to detail", "A1.2": "Difficulty sustaining attention",
  "A1.3": "Does not seem to listen", "A1.4": "Does not follow through",
  "A1.5": "Difficulty organising", "A1.6": "Avoids sustained mental effort",
  "A1.7": "Loses necessary items", "A1.8": "Easily distracted", "A1.9": "Forgetful",
  "A2.1": "Fidgets or squirms", "A2.2": "Leaves seat", "A2.3": "Restless / inappropriate activity",
  "A2.4": "Difficulty engaging quietly", "A2.5": "Often ‘on the go’", "A2.6": "Talks excessively",
  "A2.7": "Blurts out answers", "A2.8": "Difficulty waiting", "A2.9": "Interrupts or intrudes",
};

export const criterionIds = Object.keys(criteriaLabels);

export const criteriaGroups = [
  { prefix: "A1.", title: "A1. Inattention Criteria" },
  { prefix: "A2.", title: "A2. Hyperactivity / Impulsivity Criteria" },
];

export const criterionOutcomeLabels = {
  met: "Met",
  not_met: "Not met",
  insufficient: "Insufficient evidence",
  unreviewed: "Not reviewed",
};
