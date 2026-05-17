import React, { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useScroll, useTransform } from "framer-motion";
import { ArrowRight, TrendingUp, BarChart3, Network, Zap } from "lucide-react";

// ─── Logo ────────────────────────────────────────────────────────────────────
function LogoIcon({ className = "w-7 h-7" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 256 256"
      fill="currentColor"
      className={className}
      aria-hidden
    >
      <path d="M128.005 191.173C128.448 156.208 156.93 128 192 128L192 64L128 64C128 99.346 99.346 128 64 128L64 192L128 192ZM192 256L64 256C28.654 256 0 227.346 0 192L0 64L64 64L64 0L192 0C227.346 0 256 28.654 256 64L256 192L192 192Z" />
    </svg>
  );
}

// ─── Pill button (shared) ─────────────────────────────────────────────────────
function PillButton({
  children,
  onClick,
  dark = true,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  dark?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-3 text-base font-medium pl-8 pr-2 py-2 rounded-full transition-colors duration-200 ${
        dark
          ? "bg-white text-black hover:bg-white/90"
          : "bg-black text-white hover:bg-gray-900"
      }`}
    >
      {children}
      <span className={`${dark ? "bg-black" : "bg-white"} rounded-full p-2`}>
        <ArrowRight
          className={`w-4 h-4 ${dark ? "text-white" : "text-black"}`}
        />
      </span>
    </button>
  );
}

// ─── Brand Marquee items ──────────────────────────────────────────────────────
const HERO_BRANDS = [
  {
    label: "Finnhub",
    style: {
      fontFamily: "Georgia, serif",
      fontWeight: 700,
      letterSpacing: "-0.02em",
      fontSize: 15,
    },
  },
  {
    label: "Alpha Vantage",
    style: {
      fontFamily: "Arial, sans-serif",
      fontWeight: 900,
      letterSpacing: "0.06em",
      fontSize: 12,
      textTransform: "uppercase" as const,
    },
  },
  {
    label: "Binance",
    style: {
      fontFamily: "'Trebuchet MS', sans-serif",
      fontWeight: 600,
      letterSpacing: "0.01em",
      fontSize: 15,
    },
  },
  {
    label: "OpenAI",
    style: {
      fontFamily: "'Courier New', monospace",
      fontWeight: 700,
      letterSpacing: "0.10em",
      fontSize: 13,
      textTransform: "uppercase" as const,
    },
  },
  {
    label: "NebulaGraph",
    style: {
      fontFamily: "Palatino, serif",
      fontWeight: 400,
      letterSpacing: "-0.01em",
      fontSize: 16,
    },
  },
  {
    label: "NewsData.io",
    style: {
      fontFamily: "Impact, 'Arial Narrow', sans-serif",
      fontWeight: 400,
      letterSpacing: "0.04em",
      fontSize: 14,
    },
  },
  {
    label: "Qdrant",
    style: {
      fontFamily: "Verdana, sans-serif",
      fontWeight: 700,
      letterSpacing: "-0.03em",
      fontSize: 13,
    },
  },
];

const BACKER_BRANDS = [
  {
    label: "OpenAI",
    style: {
      fontFamily: "'Times New Roman', serif",
      fontWeight: 400,
      letterSpacing: "0.02em",
      fontSize: 14,
    },
  },
  {
    label: "Anthropic",
    style: {
      fontFamily: "'Arial Black', sans-serif",
      fontWeight: 900,
      letterSpacing: "0.06em",
      fontSize: 14,
    },
  },
  {
    label: "Finnhub",
    style: {
      fontFamily: "Impact, sans-serif",
      fontWeight: 700,
      letterSpacing: "0.05em",
      fontSize: 16,
    },
  },
  {
    label: "Binance",
    style: {
      fontFamily: "Georgia, serif",
      fontWeight: 600,
      letterSpacing: "-0.02em",
      fontSize: 15,
    },
  },
  {
    label: "NebulaGraph",
    style: {
      fontFamily: "Helvetica, sans-serif",
      fontWeight: 700,
      letterSpacing: "-0.01em",
      fontSize: 15,
    },
  },
  {
    label: "Qdrant",
    style: {
      fontFamily: "Verdana, sans-serif",
      fontWeight: 700,
      letterSpacing: "0.06em",
      fontSize: 13,
      textTransform: "uppercase" as const,
    },
  },
  {
    label: "NewsData",
    style: {
      fontFamily: "'Courier New', monospace",
      fontWeight: 700,
      letterSpacing: "0.15em",
      fontSize: 13,
    },
  },
  {
    label: "Redis",
    style: {
      fontFamily: "Palatino, serif",
      fontWeight: 500,
      letterSpacing: "0.03em",
      fontSize: 14,
    },
  },
];

// ─── Feature cards data ───────────────────────────────────────────────────────
const FEATURE_CARDS = [
  {
    colSpan: "lg:col-span-2",
    bg: "bg-gradient-to-br from-[#0f62fe]/20 to-[#0a0a0f] border border-[#0f62fe]/30",
    title: "Live Market\nIntelligence",
    icon: <TrendingUp className="w-6 h-6 text-[#0f62fe]" />,
    body: "Real-time quotes from Finnhub, Alpha Vantage, and Binance with a two-level semantic + Redis cache waterfall. Always fresh, always fast.",
  },
  {
    colSpan: "lg:col-span-1",
    bg: "bg-[#16161f] border border-white/10",
    title: "Supply Chain\nCausality",
    icon: <Network className="w-6 h-6 text-white/40" />,
    body: "Multi-hop graph traversal over 57 companies and 20 commodities reveals hidden exposure to any disruption instantly.",
  },
  {
    colSpan: "lg:col-span-1",
    bg: "bg-[#16161f] border border-white/10",
    title: "Multi-Agent\nReasoning",
    icon: <Zap className="w-6 h-6 text-white/40" />,
    body: "Bull and Bear agents run concurrently. A Judge agent synthesises both into a decisive investment verdict with confidence score.",
  },
];

// ─── Nav link map ─────────────────────────────────────────────────────────────
const NAV_LINKS: { label: string; sectionId: string }[] = [
  { label: "Market Data",  sectionId: "market-data" },
  { label: "Analysis",     sectionId: "analysis" },
  { label: "Supply Chain", sectionId: "market-data" },
  { label: "News",         sectionId: "use-cases" },
  { label: "About",        sectionId: "about" },
];

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ─── Navbar ───────────────────────────────────────────────────────────────────
function Navbar({ onOpenApp }: { onOpenApp: () => void }) {
  return (
    <nav className="absolute top-0 left-0 right-0 z-20 px-6 py-5">
      <div className="max-w-[88rem] mx-auto flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <LogoIcon className="w-7 h-7 text-white" />
          <span className="text-2xl font-medium tracking-tight text-white">
            QuantVex
          </span>
        </div>

        {/* Center links */}
        <div className="hidden md:flex items-center gap-8">
          {NAV_LINKS.map(({ label, sectionId }) => (
            <button
              key={label}
              type="button"
              onClick={() => scrollTo(sectionId)}
              className="text-base text-white/70 hover:text-white font-medium transition-colors duration-200"
            >
              {label}
            </button>
          ))}
        </div>

        {/* CTA */}
        <button
          onClick={onOpenApp}
          className="bg-white text-black text-base font-medium px-7 py-2.5 rounded-full hover:bg-white/90 transition-colors duration-200"
        >
          Open App
        </button>
      </div>
    </nav>
  );
}

// ─── Hero ─────────────────────────────────────────────────────────────────────
function HeroSection({ onGetStarted }: { onGetStarted: () => void }) {
  const heroRef = useRef<HTMLDivElement>(null);
  const { scrollY } = useScroll();
  const y = useTransform(scrollY, [0, 500], [0, -80]);
  const opacity = useTransform(scrollY, [0, 400], [1, 0.3]);

  return (
    <div className="flex-1 px-6 pt-20 pb-6 flex items-end">
      <div
        ref={heroRef}
        className="relative w-full rounded-2xl overflow-hidden"
        style={{ height: "calc(100vh - 96px)" }}
      >
        {/* Video background */}
        <video
          autoPlay
          muted
          loop
          playsInline
          className="absolute inset-0 w-full h-full object-cover"
        >
          <source src="/bd-video.mp4" type="video/mp4" />
        </video>

        {/* Gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-r from-black/40 to-transparent" />

        {/* Content */}
        <motion.div
          style={{ y, opacity }}
          className="relative z-10 flex flex-col items-start h-full p-8 md:p-12 pt-32 md:pt-36"
        >
          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: "easeOut" }}
            className="text-white text-5xl md:text-7xl font-medium leading-tight max-w-2xl mb-4"
            style={{ letterSpacing: "-0.04em" }}
          >
            Market Intelligence.
            <br />
            Live.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.15, ease: "easeOut" }}
            className="text-white/70 text-base md:text-lg max-w-md mb-8 leading-relaxed"
          >
            Real-time market data, supply chain causality, and adversarial AI
            reasoning — grounded in live tool calls, never guesswork.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.3, ease: "easeOut" }}
          >
            <PillButton onClick={onGetStarted} dark={false}>
              Get Started
            </PillButton>
          </motion.div>

          {/* Brand marquee */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.5 }}
            className="mt-16 md:mt-24 w-full max-w-lg overflow-hidden"
          >
            <div className="marquee-track">
              {[...HERO_BRANDS, ...HERO_BRANDS].map((brand, i) => (
                <span
                  key={i}
                  className="mx-7 shrink-0 text-white/50 whitespace-nowrap"
                  style={brand.style}
                >
                  {brand.label}
                </span>
              ))}
            </div>
          </motion.div>
        </motion.div>
      </div>
    </div>
  );
}

// ─── Info Section ─────────────────────────────────────────────────────────────
function InfoSection({ onExplore }: { onExplore: () => void }) {
  return (
    <section id="market-data" className="bg-[#0a0a0f] px-6 py-24">
      <div className="max-w-[88rem] mx-auto">
        {/* Row 1 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-12 mb-16 items-start">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <h2
              className="text-white text-4xl md:text-5xl font-medium leading-tight mb-8"
              style={{ letterSpacing: "-0.03em" }}
            >
              Meet QuantVex.
            </h2>
            <PillButton onClick={onExplore} dark={false}>
              Explore Platform
            </PillButton>
          </motion.div>

          <motion.p
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-white/70 text-2xl md:text-3xl leading-relaxed"
          >
            QuantVex is an AI-powered financial intelligence platform. Real-time
            quotes, supply chain causality traversal, live news impact, and
            adversarial multi-agent reasoning — all grounded in live data.
          </motion.p>
        </div>

        {/* Feature cards */}
        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.1 } },
          }}
        >
          {FEATURE_CARDS.map((card, i) => (
            <motion.div
              key={i}
              variants={{
                hidden: { opacity: 0, y: 30 },
                visible: { opacity: 1, y: 0, transition: { duration: 0.5 } },
              }}
              className={`${card.colSpan} ${card.bg} rounded-2xl p-7 min-h-80 flex flex-col justify-between`}
            >
              <div className="flex items-start justify-between mb-4">
                <h3
                  className="text-white text-2xl font-medium leading-snug whitespace-pre-line"
                  style={{ letterSpacing: "-0.02em" }}
                >
                  {card.title}
                </h3>
                {card.icon}
              </div>
              <p className="text-white/60 text-base leading-relaxed">
                {card.body}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

// ─── Backed By Section ────────────────────────────────────────────────────────
function BackedBySection() {
  return (
    <section className="bg-[#0a0a0f] px-6 py-16 border-t border-white/5">
      <div className="max-w-[88rem] mx-auto grid grid-cols-1 md:grid-cols-4 gap-8 items-center">
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-white/60 text-base leading-relaxed"
        >
          Built on best-in-class
          <br />
          infrastructure and data partners.
        </motion.p>

        <div className="md:col-span-3 overflow-hidden">
          <div className="backers-track">
            {[...BACKER_BRANDS, ...BACKER_BRANDS].map((brand, i) => (
              <span
                key={i}
                className="mx-10 shrink-0 text-white/40 whitespace-nowrap"
                style={brand.style}
              >
                {brand.label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── Use Cases Section ────────────────────────────────────────────────────────
function UseCasesSection({ onExplore }: { onExplore: () => void }) {
  return (
    <section id="use-cases" className="bg-[#0a0a0f] px-6 py-24">
      <div className="max-w-[88rem] mx-auto grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
        {/* Left */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="md:pr-12 md:pt-2"
        >
          <p className="text-white/60 text-sm mb-2 tracking-wide">
            QuantVex in Practice
          </p>
          <h2
            className="text-white text-5xl md:text-6xl font-medium leading-none mb-6"
            style={{ letterSpacing: "-0.04em" }}
          >
            Use Cases
          </h2>
          <p className="text-white/60 text-base leading-relaxed max-w-sm">
            QuantVex powers investment desks, portfolio managers, and fintech
            builders who need real-time data, causal supply chain maps, and AI
            reasoning on demand — not static dashboards.
          </p>
        </motion.div>

        {/* Right — video card */}
        <motion.div
          id="analysis"
          initial={{ opacity: 0, scale: 0.97 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7 }}
          className="relative rounded-3xl overflow-hidden min-h-[600px] md:min-h-[720px]"
        >
          <video
            autoPlay
            muted
            loop
            playsInline
            className="absolute inset-0 w-full h-full object-cover"
          >
            <source src="/video2.mp4" type="video/mp4" />
            <source src="/bd-video.mp4" type="video/mp4" />
          </video>
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />

          <div className="relative z-10 p-10 md:p-12 flex flex-col justify-end h-full">
            <div className="flex items-center gap-2 mb-2">
              <BarChart3 className="w-5 h-5 text-[#0f62fe]" />
              <span className="text-white/60 text-sm font-medium tracking-wide">
                INVESTMENT ANALYSIS
              </span>
            </div>
            <h3
              className="text-white text-4xl md:text-5xl font-medium leading-tight mb-5"
              style={{ letterSpacing: "-0.03em" }}
            >
              Multi-Agent
              <br />
              Reasoning
            </h3>
            <p className="text-white/70 text-base max-w-md mb-8 leading-relaxed">
              Run concurrent Bull and Bear agent theses on any ticker. A Judge
              agent synthesises both sides into a decisive STRONG BUY → STRONG
              SELL verdict with confidence scoring.
            </p>
            <button
              onClick={onExplore}
              className="inline-flex items-center gap-3 group w-fit"
            >
              <span className="w-9 h-9 rounded-full bg-white/20 backdrop-blur flex items-center justify-center group-hover:bg-white/30 transition-colors">
                <ArrowRight className="w-4 h-4 text-white" />
              </span>
              <span className="text-white text-base font-medium">
                Try Analysis
              </span>
            </button>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

// ─── About Section ────────────────────────────────────────────────────────────
const ABOUT_PILLARS = [
  {
    title: "Open by Design",
    body: "Built on open standards — MCP, NebulaGraph, Qdrant, Redis. No black boxes. Every data hop is inspectable.",
  },
  {
    title: "Adversarial Reasoning",
    body: "Bull and Bear agents argue opposite theses. A Judge synthesises both. Confidence scores are earned, not assumed.",
  },
  {
    title: "Live Grounding",
    body: "Every answer is backed by a live tool call — Finnhub, Alpha Vantage, or NewsData.io. Zero hallucinated data.",
  },
];

function AboutSection({ onOpenApp }: { onOpenApp: () => void }) {
  return (
    <section id="about" className="bg-[#0a0a0f] px-6 py-24 border-t border-white/5">
      <div className="max-w-[88rem] mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-12 mb-16 items-start">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <p className="text-white/60 text-sm mb-2 tracking-wide">
              About QuantVex
            </p>
            <h2
              className="text-white text-5xl md:text-6xl font-medium leading-none mb-8"
              style={{ letterSpacing: "-0.04em" }}
            >
              Built for
              <br />
              Clarity.
            </h2>
            <PillButton onClick={onOpenApp} dark={false}>
              Start for Free
            </PillButton>
          </motion.div>

          <motion.p
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-white/70 text-2xl md:text-3xl leading-relaxed"
          >
            QuantVex was built because financial AI deserved more than a chatbot
            wrapper — it needed real data, causal reasoning, and adversarial
            debate baked in from the start.
          </motion.p>
        </div>

        <motion.div
          className="grid grid-cols-1 sm:grid-cols-3 gap-4"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.1 } },
          }}
        >
          {ABOUT_PILLARS.map((pillar, i) => (
            <motion.div
              key={i}
              variants={{
                hidden: { opacity: 0, y: 30 },
                visible: { opacity: 1, y: 0, transition: { duration: 0.5 } },
              }}
              className="bg-[#16161f] border border-white/10 rounded-2xl p-7 min-h-52 flex flex-col justify-between"
            >
              <h3
                className="text-white text-2xl font-medium leading-snug mb-4"
                style={{ letterSpacing: "-0.02em" }}
              >
                {pillar.title}
              </h3>
              <p className="text-white/60 text-base leading-relaxed">
                {pillar.body}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

// ─── Footer ───────────────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer className="bg-[#0a0a0f] border-t border-white/5 px-6 py-10">
      <div className="max-w-[88rem] mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-white/40">
          <LogoIcon className="w-5 h-5" />
          <span className="text-sm font-medium">
            QuantVex © {new Date().getFullYear()}
          </span>
        </div>
        <p className="text-white/30 text-sm">
          AI-powered financial intelligence. All data grounded in live tool
          calls.
        </p>
      </div>
    </footer>
  );
}

// ─── LandingPage ─────────────────────────────────────────────────────────────
export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col bg-[#0a0a0f] min-h-screen">
      {/* Hero — full screen wrapper */}
      <div className="h-screen flex flex-col overflow-hidden relative">
        <Navbar onOpenApp={() => navigate("/dashboard")} />
        <HeroSection onGetStarted={() => navigate("/signup")} />
      </div>

      {/* Below-fold sections */}
      <InfoSection onExplore={() => navigate("/dashboard")} />
      <BackedBySection />
      <UseCasesSection onExplore={() => navigate("/chat")} />
      <AboutSection onOpenApp={() => navigate("/signup")} />
      <Footer />
    </div>
  );
}
