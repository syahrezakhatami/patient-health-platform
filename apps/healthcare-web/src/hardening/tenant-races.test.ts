import { describe, expect, it } from "vitest";

import { TenantLoadCoordinator } from "../tenant/generation";

async function wait(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

describe("stale organization response strategy", () => {
  it("keeps B when A resolves last", async () => {
    const coordinator = new TenantLoadCoordinator();
    let committed: string | null = null;

    async function load(org: string, delayMs: number): Promise<void> {
      const { generation, signal } = coordinator.begin();
      await wait(delayMs);
      if (signal.aborted || !coordinator.isCurrent(generation)) {
        return;
      }
      committed = org;
    }

    const first = load("A", 40);
    const second = load("B", 5);
    await Promise.all([first, second]);
    expect(committed).toBe("B");
  });

  it("ends on final A after rapid A -> B -> A", async () => {
    const coordinator = new TenantLoadCoordinator();
    let committed: string | null = null;

    async function load(org: string, delayMs: number): Promise<void> {
      const { generation, signal } = coordinator.begin();
      await wait(delayMs);
      if (signal.aborted || !coordinator.isCurrent(generation)) {
        return;
      }
      committed = org;
    }

    const loads = [load("A", 30), load("B", 20), load("A", 5)];
    await Promise.all(loads);
    expect(committed).toBe("A");
  });

  it("does not let a late facility A1 overwrite A2", async () => {
    const coordinator = new TenantLoadCoordinator();
    let facility: string | null = null;

    async function select(id: string, delayMs: number): Promise<void> {
      const { generation, signal } = coordinator.begin();
      await wait(delayMs);
      if (signal.aborted || !coordinator.isCurrent(generation)) {
        return;
      }
      facility = id;
    }

    await Promise.all([select("A1", 25), select("A2", 5)]);
    expect(facility).toBe("A2");
  });
});
