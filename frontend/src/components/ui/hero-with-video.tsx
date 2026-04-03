import React, { useState, useEffect } from "react";
import { ArrowRight, Menu } from "lucide-react";

interface NavbarHeroProps {
  brandName?: string;
  heroTitle?: string;
  heroDescription?: string;
  backgroundImage?: string;
  videobackground?: string;
  onNavigateChat?: () => void;
  onNavigateDashboard?: () => void;
}

const NavbarHero: React.FC<NavbarHeroProps> = ({
  brandName = "Finance MCP",
  heroTitle = "AI-Powered Market Intelligence",
  heroDescription = "A real-time financial analysis platform combining live market data, knowledge-graph reasoning, and AI-driven supply-chain intelligence.",
  backgroundImage = "/earth-bg.png",
  videobackground = "/bd-video.mp4",
  onNavigateChat,
  onNavigateDashboard,
}) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, []);

  return (
    <main
      className="absolute inset-0 overflow-y-auto text-white"
      style={{ fontFamily: '"Satoshi", "Geist", "Inter", sans-serif' }}
    >
      <div className="fixed inset-0 overflow-hidden bg-black">
        <video
          src={videobackground}
          autoPlay
          loop
          muted
          playsInline
          className="absolute inset-0 h-full w-full object-cover"
        />

        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(0,0,0,0.55),rgba(0,0,0,0.72))]" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-black/8 to-black/20" />
      </div>

      <div className="relative z-10 w-full max-w-[1200px] mx-auto px-5 sm:px-8 lg:px-10 pb-16 sm:pb-24">
        {/* --- Navbar --- */}
        <div className="sticky top-0 z-20 pt-5">
          <div className="flex items-center justify-between gap-4 rounded-2xl border border-white/[0.08] bg-[rgba(0,0,0,0.45)] px-5 py-4 backdrop-blur-xl">
            <div className="flex items-center gap-6">
              <div className="cursor-pointer flex-shrink-0 text-xl font-bold tracking-[-0.02em] text-white sm:text-2xl">
                {brandName}
              </div>
              <nav className="hidden lg:flex font-medium text-white/72">
                <ul className="flex items-center space-x-2">
                  <li>
                    <a
                      href="/"
                      className="rounded-lg px-3 py-2 text-sm text-[#8FABD4] transition-colors hover:text-white"
                    >
                      Home
                    </a>
                  </li>
                  <li>
                    <a
                      href="/dashboard"
                      className="rounded-lg px-3 py-2 text-sm transition-colors hover:text-[#8FABD4]"
                    >
                      Dashboard
                    </a>
                  </li>
                  <li>
                    <a
                      href="/chat"
                      className="rounded-lg px-3 py-2 text-sm transition-colors hover:text-[#8FABD4]"
                    >
                      AI Chat
                    </a>
                  </li>
                </ul>
              </nav>
            </div>

            <div className="flex items-center gap-3">
              <div className="lg:hidden relative">
                <button
                  onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                  className="rounded-xl border border-white/10 bg-white/5 p-2 text-white transition-colors hover:bg-white/10"
                  aria-label="Open navigation menu"
                >
                  <Menu className="h-6 w-6" />
                </button>
                {isMobileMenuOpen && (
                  <ul className="absolute right-0 top-full z-30 mt-2 w-56 rounded-2xl border border-white/10 bg-[rgba(0,0,0,0.72)] p-2 shadow-2xl backdrop-blur-xl">
                    <li>
                      <a
                        href="/"
                        className="block rounded-lg px-3 py-2 text-sm text-[#8FABD4] hover:bg-white/5"
                      >
                        Home
                      </a>
                    </li>
                    <li>
                      <a
                        href="/dashboard"
                        className="block rounded-lg px-3 py-2 text-sm text-white hover:bg-white/5"
                      >
                        Dashboard
                      </a>
                    </li>
                    <li>
                      <a
                        href="/chat"
                        className="block rounded-lg px-3 py-2 text-sm text-white hover:bg-white/5"
                      >
                        AI Chat
                      </a>
                    </li>
                    <li className="mt-2 space-y-2 border-t border-white/10 pt-2">
                      <button
                        onClick={onNavigateDashboard}
                        className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#8FABD4] bg-[rgba(143,171,212,0.15)] px-3 py-2.5 text-sm font-medium text-white transition duration-200 ease-out hover:-translate-y-0.5 hover:bg-[rgba(143,171,212,0.22)]"
                      >
                        Analytics Dashboard
                        <ArrowRight className="h-4 w-4" />
                      </button>
                    </li>
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* --- Hero Section --- */}
        <div className="mx-auto mt-[120px] text-center">
          <div className="relative mx-auto max-w-[860px]">
            <div className="hero-glow absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2" />
            <h1 className="hero-fade-up hero-headline-gradient relative z-10 text-[40px] font-bold leading-[1.08] tracking-[-0.02em] sm:text-[56px] lg:text-[64px]">
              {heroTitle}
            </h1>
            <p className="hero-fade-up animation-delay-1 mt-6 whitespace-pre-line text-base font-normal leading-[1.6] text-gray-300 sm:text-md lg:text-[20px] max-w-[720px] mx-auto">
              {heroDescription}
            </p>
            <div className="hero-fade-up animation-delay-2 mt-8 flex items-center justify-center gap-4 flex-wrap">
              <button
                onClick={onNavigateChat}
                className="hero-primary-button flex items-center gap-2 rounded-[10px] px-[26px] py-[14px] text-[16px] font-medium text-white transition duration-200 ease-out hover:-translate-y-0.5 hover:scale-[1.04]"
              >
                AI Analysis
                <ArrowRight className="h-4 w-4" />
              </button>
              <button
                onClick={onNavigateDashboard}
                className="hero-secondary-button flex items-center gap-2 rounded-[10px] px-[26px] py-[14px] text-[16px] font-medium text-white transition duration-200 ease-out hover:-translate-y-0.5 hover:scale-[1.04]"
              >
                Analytics Dashboard
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Features Grid */}
        <div className="hero-fade-up animation-delay-3 mt-20 grid grid-cols-1 gap-7 md:grid-cols-2 xl:grid-cols-4">
          <div className="hero-card rounded-2xl p-6">
            <h3 className="mb-3 text-lg font-semibold text-white">
              Real-Time Market Data
            </h3>
            <p className="text-sm leading-6 text-white/78">
              Live financial APIs deliver instant stock, crypto, and market
              pricing with minimal latency.
            </p>
          </div>
          <div className="hero-card rounded-2xl p-6">
            <h3 className="mb-3 text-lg font-semibold text-white">
              Supply Chain Intelligence
            </h3>
            <p className="text-sm leading-6 text-white/78">
              A knowledge graph models dependencies between companies and
              commodities to trace cascading impacts.
            </p>
          </div>
          <div className="hero-card rounded-2xl p-6">
            <h3 className="mb-3 text-lg font-semibold text-white">
              AI Financial Analyst
            </h3>
            <p className="text-sm leading-6 text-white/78">
              Ask complex market questions and receive structured analysis
              powered by MCP tools and real-time data.
            </p>
          </div>
          <div className="hero-card rounded-2xl p-6">
            <h3 className="mb-3 text-lg font-semibold text-white">
              Event-Driven Insights
            </h3>
            <p className="text-sm leading-6 text-white/78">
              News ingestion automatically detects economic events and evaluates
              their downstream market impact.
            </p>
          </div>
        </div>
      </div>
    </main>
  );
};

export { NavbarHero };
