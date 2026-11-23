import { useEffect, useState } from "react";
import {
  HANDOFF_SCENARIOS,
  handoffReducer,
  initialHandoff,
  type HandoffAction,
  type HandoffScenario,
  type HandoffState,
} from "@/lib/handoff";

export function useHandoffDemo(replayEnabled = true) {
  const [selected, setSelected] = useState<HandoffScenario>("success");
  const [records, setRecords] = useState<HandoffState[]>(() =>
    HANDOFF_SCENARIOS.map((scenario) => initialHandoff(scenario.id)),
  );
  const state = records.find((record) => record.scenario === selected) ?? initialHandoff(selected);
  const dispatch = (action: HandoffAction) =>
    setRecords((current) =>
      current.map((record) =>
        record.scenario === selected ? handoffReducer(record, action) : record,
      ),
    );
  useEffect(() => {
    if (!replayEnabled || !state.playing || selected === "success") return;
    const timer = setTimeout(
      () =>
        setRecords((current) =>
          current.map((record) =>
            record.scenario === selected ? handoffReducer(record, { type: "advance" }) : record,
          ),
        ),
      1600,
    );
    return () => clearTimeout(timer);
  }, [replayEnabled, state.playing, state.step, selected]);
  const reset = () =>
    setRecords((current) =>
      current.map((record) => (record.scenario === selected ? initialHandoff(selected) : record)),
    );
  return { state, records, selected, select: setSelected, dispatch, reset };
}
export type HandoffDemo = ReturnType<typeof useHandoffDemo>;
