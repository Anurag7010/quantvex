import React, { useEffect, useRef, useState } from "react";
import { StructuredAnalysisMessage } from "./analysis";

interface Props {
  content: string;
}

const CHAR_INTERVAL_MS = 9;

const TypewriterMessage: React.FC<Props> = ({ content }) => {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);
  const iRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    iRef.current = 0;
    setDisplayed("");
    setDone(false);

    timerRef.current = setInterval(() => {
      iRef.current += 1;
      setDisplayed(content.slice(0, iRef.current));
      if (iRef.current >= content.length) {
        if (timerRef.current) clearInterval(timerRef.current);
        setDone(true);
      }
    }, CHAR_INTERVAL_MS);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [content]);

  if (done) {
    return <StructuredAnalysisMessage content={content} />;
  }

  return (
    <p className="whitespace-pre-wrap text-sm leading-7 text-neutral-200">
      {displayed}
      <span className="typewriter-cursor" aria-hidden="true" />
    </p>
  );
};

export default TypewriterMessage;
