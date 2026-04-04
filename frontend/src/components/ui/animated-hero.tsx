import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { MoveRight } from "lucide-react";
import { Button } from "./button";
import { FocusRail, type FocusRailItem } from "./focus-rail";

interface HeroProps {
  onNavigateAnalysis?: () => void;
  onNavigateDashboard?: () => void;
}

const FEATURE_ITEMS: FocusRailItem[] = [
  {
    id: 1,
    title: "Live Market Feed",
    description:
      "Real-time pricing across equities, crypto, and global indices.",
    imageSrc:
      "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?q=80&w=2940&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D?q=80&w=1200&auto=format&fit=crop",
  },
  {
    id: 2,
    title: "Dependency Intelligence",
    description:
      "Maps supply chain links to identify multi-hop market exposure.",
    imageSrc:
      "https://images.unsplash.com/photo-1446776653964-20c1d3a81b06?q=80&w=2942&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D?q=80&w=1200&auto=format&fit=crop",
  },
  {
    id: 3,
    title: "Event Intelligence Engine",
    description:
      "Converts global news into structured impact signals for traded assets.",
    imageSrc:
      "https://images.unsplash.com/photo-1675973094287-f4af3e49bb3d?q=80&w=2940&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D?q=80&w=1200&auto=format&fit=crop",
  },
  {
    id: 4,
    title: "Autonomous Market Analyst",
    description:
      "Queries scenarios and returns data-backed financial insights.",
    imageSrc:
      "https://images.unsplash.com/photo-1744473755637-e09f0c2fab41?q=80&w=2940&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D?q=80&w=1200&auto=format&fit=crop",
  },
  {
    id: 5,
    title: "Adversarial Reasoning Engine",
    description: "Bull and Bear agents evaluate outcomes before conclusions.",
    imageSrc:
      "https://images.financialexpressdigital.com/2025/03/MKT.freepui.jpg?q=80&w=1200&auto=format&fit=crop",
  },
];

function Hero({ onNavigateAnalysis, onNavigateDashboard }: HeroProps) {
  const [titleNumber, setTitleNumber] = useState(0);
  const titles = useMemo(
    () => ["precision", "performance", "accuracy", "intelligence"],
    [],
  );

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      if (titleNumber === titles.length - 1) {
        setTitleNumber(0);
      } else {
        setTitleNumber(titleNumber + 1);
      }
    }, 2000);
    return () => clearTimeout(timeoutId);
  }, [titleNumber, titles]);

  return (
    <section className="relative w-full overflow-hidden bg-[linear-gradient(180deg,#000000_0%,#04070f_56%,#0A0F1C_100%)] text-white">
      <div className="absolute inset-0 overflow-hidden bg-black">
        <video
          src="/bd-video.mp4"
          //src="/video2.mp4"
          autoPlay
          loop
          muted
          playsInline
          className="absolute inset-0 h-full w-full object-cover opacity-55"
        />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(74,112,169,0.15),transparent)]" />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(0,0,0,0.45),rgba(0,0,0,0.78))]" />
      </div>

      <div className="sticky top-0 z-30 border-b border-white/10 bg-black/25 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-6">
          <div className="text-sm font-semibold tracking-[0.08em] text-white/90">
            QuantVex
          </div>
          <div className="flex items-center gap-5 text-sm text-neutral-300">
            <a
              href="/"
              className="transition hover:scale-[1.02] hover:text-white"
            >
              Home
            </a>
            <a
              href="/dashboard"
              className="transition hover:scale-[1.02] hover:text-white"
            >
              Dashboard
            </a>
            <a
              href="/chat"
              className="transition hover:scale-[1.02] hover:text-white"
            >
              Analysis
            </a>
          </div>
        </div>
      </div>

      <div className="relative z-10 mx-auto w-full max-w-6xl px-6">
        <div className="flex min-h-[60vh] items-center justify-center py-24">
          <div className="flex w-full max-w-4xl -translate-y-6 md:-translate-y-8 flex-col items-center gap-8 text-center">
            <div className="flex flex-col gap-4">
              <h1 className="max-w-3xl text-7xl font-bold tracking-tight leading-[1.08] md:text-7xl lg:text-8xl">
                <span className="text-white">QuantVex</span>
              </h1>
              <h1 className="max-w-3xl text-center text-3xl font-semibold tracking-tight leading-[1.08] md:text-5xl lg:text-6xl">
                <span className="text-white">Engineered for</span>
                <span className="relative flex w-full justify-center overflow-hidden text-center text-[#9cccdf] md:pb-4 md:pt-1">
                  &nbsp;
                  {titles.map((title, index) => (
                    <motion.span
                      key={index}
                      className="absolute font-semibold"
                      initial={{ opacity: 0, y: "-100" }}
                      transition={{ type: "spring", stiffness: 50 }}
                      animate={
                        titleNumber === index
                          ? {
                              y: 0,
                              opacity: 1,
                            }
                          : {
                              y: titleNumber > index ? -150 : 150,
                              opacity: 0,
                            }
                      }
                    >
                      {title}
                    </motion.span>
                  ))}
                </span>
              </h1>

              <p className="max-w-2xl text-center text-base leading-relaxed tracking-tight text-neutral-400">
                A unified system combining real-time market data, supply chain
                intelligence, and multi-agent financial reasoning for structured
                decision-making.
              </p>
            </div>

            <div className="flex w-full flex-col justify-center gap-3 sm:flex-row">
              <Button
                size="lg"
                className="gap-4 bg-[#6589b2] text-white transition-transform hover:scale-[1.02] hover:bg-[#8FABD4]"
                onClick={onNavigateAnalysis}
              >
                Run Analysis <MoveRight className="h-4 w-4" />
              </Button>

              <Button
                size="lg"
                variant="outline"
                className="gap-4 border-[#8FABD4] bg-transparent text-white transition-transform hover:scale-[1.02] hover:bg-[#8FABD4]/10 hover:text-white"
                onClick={onNavigateDashboard}
              >
                Open Dashboard <MoveRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-gradient-to-b from-transparent to-[#0A0F1C]" />

        <div className="relative z-20 -mt-16 py-24">
          <div className="mx-auto w-full max-w-6xl rounded-2xl border border-white/10 bg-white/5 p-6 backdrop-blur-xl">
            <div className="mb-8 text-center">
              <p className="mb-3 text-lg font-medium uppercase tracking-[0.16em] text-[#8FABD4]">
                Core Features
              </p>
              <h2 className="text-3xl font-semibold tracking-tight text-white">
                Built for Intelligent Market Analysis
              </h2>
            </div>
            <FocusRail
              items={FEATURE_ITEMS}
              autoPlay={true}
              interval={2200}
              loop={true}
              className="bg-transparent"
            />
          </div>
        </div>

        <footer className="border-t border-white/10 py-24">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 text-neutral-400 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-base font-semibold text-white">QuantVex</p>
              <p className="mt-2 text-sm">
                AI-powered market intelligence platform.
              </p>
            </div>
            <div className="flex gap-6 text-sm">
              <a
                href="/https://github.com/Anurag7010/finance-mcp"
                className="transition hover:text-white"
              >
                GitHub
              </a>
              <a href="/" className="transition hover:text-white">
                Documentation
              </a>
              <a
                href="mailto:contact@financemcp.com"
                className="transition hover:text-white"
              >
                Contact
              </a>
            </div>
          </div>
          <div className="mt-10 text-xs text-neutral-500">QuantVex</div>
        </footer>
      </div>
    </section>
  );
}

export { Hero };
