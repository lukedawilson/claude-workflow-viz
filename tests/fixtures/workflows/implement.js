// Example workflow — exercises the full parser subset.
// Authored for claude-workflow-viz tests

export const meta = {
  name: 'implement',
  description: 'Multi-phase change workflow: plan, develop, gate, review, verify.',
  phases: ['Plan', 'Develop', 'Gate', 'Review', 'Verify'],
};

const MAX_ROUNDS = 3;

export async function implement(input) {
  const preflight = await agent('Check working tree against the base sha.', {
    agentType: 'general-purpose',
    phase: 'Plan',
    label: 'pre-flight/head-check',
    schema: { sha: { type: 'string' } },
  });
  if (!preflight.sha) {
    return 'BLOCKED';
  }

  const planner = await agent('Split the change into reviewable slices.', {
    agentType: 'planner',
    phase: 'Plan',
    label: 'planner',
    schema: { slices: { type: 'array' }, needsContext: { type: 'string' } },
  });
  if (planner.needsContext) {
    return 'NEEDS_CONTEXT';
  }

  const baseline = await agent('Measure baseline lint/test health on the base sha.', {
    agentType: 'general-purpose',
    phase: 'Gate',
    label: 'gate-baseline',
    schema: { failures: { type: 'array' }, note: { type: 'string' } },
  });
  if (baseline.failures.length > 0) {
    return 'BLOCKED';
  }

  const outcomes = [];
  for (const slice of planner.slices) {
    const priorFindings = [];
    let round = 1;
    while (round <= MAX_ROUNDS) {
      const develop = await agent(`Implement ${slice.title}.`, {
        agentType: 'developer',
        phase: 'Develop',
        label: `${slice.id}/develop:r${round}`,
        schema: { status: { type: 'string' }, needsContext: { type: 'string' } },
      });
      if (develop.status === 'NEEDS_CONTEXT') {
        return 'NEEDS_CONTEXT';
      }
      if (develop.status === 'BLOCKED') {
        outcomes.push({ slice: slice.id, outcome: 'BLOCKED' });
        break;
      }

      const gate = await agent('Run build and tests on the working tree.', {
        agentType: 'general-purpose',
        phase: 'Gate',
        label: `${slice.id}/gate:r${round}`,
        schema: { status: { type: 'string' } },
      });
      if (gate.status !== 'green') {
        round += 1;
        continue;
      }

      const review = await agent('Review the diff against the slice contract.', {
        agentType: 'reviewer',
        phase: 'Review',
        label: `${slice.id}/review:r${round}`,
        schema: { verdict: { type: 'string' } },
      });
      if (review.verdict !== 'APPROVED') {
        priorFindings.push(review.verdict);
        round += 1;
        continue;
      }

      const findings = await agent('Hunt for bugs and test gaps.', {
        agentType: 'general-purpose',
        phase: 'Review',
        label: `${slice.id}/code-review:r${round}`,
        schema: { blocking: { type: 'boolean' } },
      });
      if (findings.blocking) {
        round += 1;
        continue;
      }

      const classify = await agent('Assess whether the diff touches shared state.', {
        agentType: 'general-purpose',
        phase: 'Verify',
        label: `${slice.id}/classify:r${round}`,
        schema: { touchesConcurrency: { type: 'boolean' } },
      });

      if (classify.touchesConcurrency && develop.changedFiles.length > 0) {
        const fsm = await agent('Run the finite-state-machine checks.', {
          agentType: 'general-purpose',
          phase: 'Verify',
          label: `${slice.id}/verify-fsm:r${round}`,
          schema: { verdict: { type: 'string' } },
        });
        if (fsm.verdict !== 'PASS') {
          round += 1;
          continue;
        }
      }

      outcomes.push({ slice: slice.id, outcome: 'DONE' });
      break;
    }
    if (round >= MAX_ROUNDS) {
      return 'BLOCKED';
    }
  }
  return 'DONE';
}
