// Example workflow — two literal-label agents in a trivial chain.
// Authored for claude-workflow-viz tests

export const meta = {
  name: 'cross-repo-check',
  description: 'Check a convention across example-org repositories.',
  phases: ['Scan', 'Summarise'],
};

export async function crossRepoCheck(input) {
  const scan = await agent('Scan the example-org repos for the convention.', {
    agentType: 'general-purpose',
    phase: 'Scan',
    label: 'scan/repos',
  });
  const summary = await agent('Summarise the findings.', {
    agentType: 'general-purpose',
    phase: 'Summarise',
    label: 'summarise/findings',
  });
  if (summary.verdict === 'CLEAN') {
    return 'DONE';
  }
  return 'BLOCKED';
}
