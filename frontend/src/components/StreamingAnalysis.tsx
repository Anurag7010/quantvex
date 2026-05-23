import React, { useEffect, useRef, useState } from "react";
import { CheckCircle, Loader2 } from "lucide-react";
import { mcpApi, SSEStep, SSEStepName, MultiAgentAnalysisData } from "../services/api";
import { StructuredAnalysisMessage } from "./analysis";

interface StepState {
  name: SSEStepName;
  label: string;
  status: "pending" | "active" | "done";
  detail?: string;
}

const STEP_LABELS: Record<SSEStepName, string> = {
  init: "Initialising",
  quote_fetch: "Fetching live quote",
  graph_trace: "Tracing supply chain",
  news_fetch: "Scanning recent news",
  bull_thesis: "Building bull thesis",
  bear_attack: "Bear attack on weakest claim",
  rebuttal: "Bull rebuttal",
  judge: "Judge evaluating transcript",
  verdict: "Verdict ready",
  done: "Complete",
};

const ORDERED_STEPS: SSEStepName[] = [
  "init",
  "quote_fetch",
  "graph_trace",
  "news_fetch",
  "bull_thesis",
  "bear_attack",
  "rebuttal",
  "judge",
  "verdict",
];

interface Props {
  ticker: string;
  query: string;
  onDone: (result: MultiAgentAnalysisData) => void;
  onError: (msg: string) => void;
}

const StreamingAnalysis: React.FC<Props> = ({ ticker, query, onDone, onError }) => {
  const [steps, setSteps] = useState<StepState[]>(
    ORDERED_STEPS.map((name) => ({ name, label: STEP_LABELS[name], status: "pending" }))
  );
  const [verdictJson, setVerdictJson] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const markStep = (name: SSEStepName, detail?: string) => {
    setSteps((prev) =>
      prev.map((s) => {
        if (s.name === name) return { ...s, status: "active", detail };
        if (ORDERED_STEPS.indexOf(s.name) < ORDERED_STEPS.indexOf(name) && s.status !== "done")
          return { ...s, status: "done" };
        return s;
      })
    );
  };

  const completeStep = (name: SSEStepName) => {
    setSteps((prev) =>
      prev.map((s) => (s.name === name ? { ...s, status: "done" } : s))
    );
  };

  useEffect(() => {
    const es = mcpApi.streamAnalysis(ticker, query, (step: SSEStep) => {
      if (step.step === "done") {
        setSteps((prev) => prev.map((s) => ({ ...s, status: "done" })));
        es.close();
        return;
      }

      if (step.step === "verdict" && step.data) {
        const result = step.data as unknown as MultiAgentAnalysisData;
        setVerdictJson(JSON.stringify(result));
        completeStep("verdict");
        onDone(result);
        return;
      }

      const detail = step.message;
      markStep(step.step, detail);

      // Auto-complete the previous step when the next fires
      const idx = ORDERED_STEPS.indexOf(step.step);
      if (idx > 0) {
        completeStep(ORDERED_STEPS[idx - 1]);
      }
    });

    es.onerror = () => {
      es.close();
      onError("Streaming connection lost. The analysis may still be running.");
    };

    esRef.current = es;
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-lg space-y-3">
      <p className="text-xs font-medium text-neutral-400 uppercase tracking-wider">
        Live reasoning trace
      </p>
      <ul className="space-y-2">
        {steps.map((s) => (
          <li key={s.name} className="flex items-start gap-3 text-sm">
            <span className="mt-0.5 flex-shrink-0">
              {s.status === "done" ? (
                <CheckCircle className="h-4 w-4 text-emerald-400" />
              ) : s.status === "active" ? (
                <Loader2 className="h-4 w-4 animate-spin text-[#8FABD4]" />
              ) : (
                <span className="block h-4 w-4 rounded-full border border-white/20" />
              )}
            </span>
            <span
              className={
                s.status === "done"
                  ? "text-neutral-300"
                  : s.status === "active"
                  ? "text-white"
                  : "text-neutral-500"
              }
            >
              {s.label}
              {s.status === "active" && s.detail && s.detail !== s.label && (
                <span className="ml-2 text-xs text-neutral-500">{s.detail}</span>
              )}
            </span>
          </li>
        ))}
      </ul>

      {verdictJson && (
        <div className="mt-4 border-t border-white/10 pt-4">
          <StructuredAnalysisMessage content={verdictJson} />
        </div>
      )}
    </div>
  );
};

export default StreamingAnalysis;
