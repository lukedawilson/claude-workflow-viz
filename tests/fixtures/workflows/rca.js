// Example workflow — deliberately contains a construct outside the
// parser subset (round-first label shape) so the parser reports UnsupportedLabel.
// Authored for claude-workflow-viz tests

export const meta = {
  name: 'rca',
  description: 'Root-cause analysis over incident notes.',
  phases: ['Investigate', 'Report'],
};

const MAX_ROUNDS = 2;

export async function rca(input) {
  const facts = await agent('Collect the incident facts.', {
    agentType: 'general-purpose',
    phase: 'Investigate',
    label: 'facts/collect:r1',
  });

  for (let round = 1; round <= MAX_ROUNDS; round += 1) {
    const theory = await agent('Propose and test the leading theory.', {
      agentType: 'general-purpose',
      phase: 'Investigate',
      label: `r${round}/investigate`,
    });
    if (theory.verdict === 'CONFIRMED') {
      return 'DONE';
    }
  }

  await agent('Write the report.', {
    agentType: 'general-purpose',
    phase: 'Report',
    label: 'report/write:r1',
  });
  return 'DONE';
}
