"use client";

import { useState, useEffect } from "react";

const questions = [
  "How will AI affect enterprise adoption?",
  "Compare expert views on AI regulation",
  "What do researchers say about AGI timelines?",
];

export function CyclicPlaceholder() {
  const [index, setIndex] = useState(0);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setFading(true);
      setTimeout(() => {
        setIndex((i) => (i + 1) % questions.length);
        setFading(false);
      }, 300);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div
      className="flex-1 px-5 py-4 text-left text-stone-400 transition-opacity duration-300"
      style={{ opacity: fading ? 0 : 1 }}
    >
      {questions[index]}
    </div>
  );
}
