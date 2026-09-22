import { Interrupt } from "@langchain/langgraph-sdk";
import { HITLRequest } from "@/components/thread/agent-inbox/types";

export function isAgentInboxInterruptSchema(
  value: unknown,
): value is Interrupt<HITLRequest> | Interrupt<HITLRequest>[] {
  const valueAsObject = Array.isArray(value) ? value[0] : value;
  if (!valueAsObject || typeof valueAsObject !== "object") {
    return false;
  }

  const interrupt = valueAsObject as Interrupt<HITLRequest>;
  if (!interrupt.value || typeof interrupt.value !== "object") {
    return false;
  }

  const hitlValue = interrupt.value as Partial<HITLRequest>;
  const { action_requests: actionRequests, review_configs: reviewConfigs } =
    hitlValue;

  if (!Array.isArray(actionRequests) || actionRequests.length === 0) {
    return false;
  }
  if (!Array.isArray(reviewConfigs) || reviewConfigs.length === 0) {
    return false;
  }

  const hasValidActionRequests = actionRequests.every((request) => {
    return (
      request &&
      typeof request === "object" &&
      "name" in request &&
      typeof request.name === "string" &&
      "args" in request &&
      request.args !== null &&
      typeof request.args === "object"
    );
  });

  const hasValidConfigs = reviewConfigs.every((config) => {
    return (
      config &&
      typeof config === "object" &&
      "action_name" in config &&
      typeof config.action_name === "string" &&
      "allowed_decisions" in config &&
      Array.isArray(config.allowed_decisions)
    );
  });

  return hasValidActionRequests && hasValidConfigs;
}

export type AnalysisInterrupt = {
  id: string;
  value: {
    kind: "scenario_selection" | "slot_completion" | "step_clarification";
    prompt: string;
    candidates?: {
      scenario_id: string;
      name: string;
      confidence?: number;
      reason?: string;
    }[];
  };
};

export function getAnalysisInterrupt(
  value: unknown,
): AnalysisInterrupt | undefined {
  if (!value || typeof value !== "object") return;
  const item = value as AnalysisInterrupt;
  if (
    typeof item.id === "string" &&
    typeof item.value?.prompt === "string" &&
    (item.value.kind === "slot_completion" ||
      item.value.kind === "step_clarification" ||
      (item.value.kind === "scenario_selection" &&
        Array.isArray(item.value.candidates) &&
        item.value.candidates.every(
          (candidate) =>
            candidate != null &&
            typeof candidate.scenario_id === "string" &&
            typeof candidate.name === "string",
        )))
  )
    return item;
}
