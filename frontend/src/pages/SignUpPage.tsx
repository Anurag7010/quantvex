import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Circle, Chrome, Github, Eye, EyeOff } from "lucide-react";

// ─── Reusable components ──────────────────────────────────────────────────────

function StepItem({
  number,
  text,
  active = false,
}: {
  number: number;
  text: string;
  active?: boolean;
}) {
  return (
    <div
      className={`flex items-center gap-4 px-5 py-4 rounded-2xl border transition-all ${
        active
          ? "bg-white text-black border-white"
          : "bg-[#1A1A1A] text-white border-transparent"
      }`}
    >
      <span
        className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold shrink-0 ${
          active ? "bg-black text-white" : "bg-white/10 text-white/40"
        }`}
      >
        {number}
      </span>
      <span className={`text-base font-medium ${active ? "text-black" : "text-white"}`}>
        {text}
      </span>
    </div>
  );
}

function SocialButton({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center justify-center gap-3 w-full h-12 bg-[#1A1A1A] border border-white/10 rounded-xl text-white text-sm font-medium hover:bg-white/5 transition-colors duration-200"
    >
      {icon}
      {label}
    </button>
  );
}

function InputGroup({
  label,
  placeholder,
  type = "text",
  children,
}: {
  label: string;
  placeholder: string;
  type?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-white">{label}</label>
      <div className="relative">
        <input
          type={type}
          placeholder={placeholder}
          className="w-full bg-[#1A1A1A] rounded-xl h-11 px-4 text-white placeholder:text-white/20 outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm"
        />
        {children}
      </div>
    </div>
  );
}

// ─── Left column (hero panel) ─────────────────────────────────────────────────
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.15, delayChildren: 0.2 } },
};
const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

function HeroPanel({ steps }: { steps: { text: string; active: boolean }[] }) {
  return (
    <div className="hidden lg:flex w-[52%] relative flex-col items-center justify-end pb-32 px-12 rounded-3xl overflow-hidden shadow-2xl h-full">
      {/* Video background */}
      <video
        autoPlay
        muted
        loop
        playsInline
        className="absolute inset-0 w-full h-full object-cover"
      >
        <source
          src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260506_081238_406ed0e3-5d83-436e-a512-0bbff7ec5b95.mp4"
          type="video/mp4"
        />
        <source src="/bd-video.mp4" type="video/mp4" />
      </video>

      {/* Hero content */}
      <motion.div
        className="relative z-10 w-full max-w-xs space-y-8"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <motion.div variants={itemVariants} className="flex items-center gap-2">
          <Circle className="w-5 h-5 fill-white text-white" />
          <span className="text-xl font-semibold tracking-tight text-white">
            QuantVex
          </span>
        </motion.div>

        <motion.div variants={itemVariants} className="space-y-3 text-center">
          <h1 className="text-4xl font-medium tracking-tight text-white whitespace-nowrap">
            Join QuantVex
          </h1>
          <p className="text-white/60 text-sm leading-relaxed px-4">
            Complete these steps to access live market intelligence.
          </p>
        </motion.div>

        <motion.div variants={itemVariants} className="space-y-3">
          {steps.map((step, i) => (
            <StepItem
              key={i}
              number={i + 1}
              text={step.text}
              active={step.active}
            />
          ))}
        </motion.div>
      </motion.div>
    </div>
  );
}

// ─── SignUpPage ───────────────────────────────────────────────────────────────
export default function SignUpPage() {
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);

  const steps = [
    { text: "Create your account", active: true },
    { text: "Connect to live data", active: false },
    { text: "Start your analysis", active: false },
  ];

  return (
    <main className="flex min-h-screen w-full bg-black selection:bg-white/30 p-2 transition-all duration-500 lg:h-screen lg:overflow-hidden lg:p-4">
      <HeroPanel steps={steps} />

      {/* Right column — form */}
      <div className="flex-1 flex flex-col items-center justify-center py-12 lg:py-6 px-4 sm:px-12 lg:px-16 xl:px-24 overflow-y-auto lg:overflow-hidden">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="w-full max-w-xl space-y-8 lg:space-y-6 sm:space-y-10"
        >
          {/* Header */}
          <div className="space-y-1">
            <h2 className="text-3xl font-medium tracking-tight text-white">
              Create New Profile
            </h2>
            <p className="text-white/40 text-sm">
              Input your basic details to begin the journey.
            </p>
          </div>

          {/* Social buttons */}
          <div className="grid grid-cols-2 gap-4">
            <SocialButton
              icon={<Chrome className="w-4 h-4" />}
              label="Google"
              onClick={() => navigate("/")}
            />
            <SocialButton
              icon={<Github className="w-4 h-4" />}
              label="Github"
              onClick={() => navigate("/")}
            />
          </div>

          {/* Divider */}
          <div className="relative flex items-center">
            <div className="flex-1 border-t border-white/10" />
            <span className="bg-black px-4 text-xs font-medium text-white/40 uppercase tracking-widest">
              Or
            </span>
            <div className="flex-1 border-t border-white/10" />
          </div>

          {/* Form */}
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <InputGroup label="First Name" placeholder="ex. Alex" />
              <InputGroup label="Last Name" placeholder="ex. Sterling" />
            </div>
            <InputGroup
              label="Email"
              type="email"
              placeholder="ex. alex.s@quantvex.io"
            />
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-white">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="Secure your account"
                  className="w-full bg-[#1A1A1A] rounded-xl h-11 px-4 pr-12 text-white placeholder:text-white/20 outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/70 transition-colors"
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
              <p className="text-white/30 text-xs">Requires at least 8 symbols.</p>
            </div>

            <button
              onClick={() => navigate("/")}
              className="w-full h-14 bg-white text-black font-semibold rounded-xl hover:bg-white/90 active:scale-[0.98] transition-all duration-200 mt-4"
            >
              Create Account
            </button>
          </div>

          {/* Footer link */}
          <p className="text-center text-white/40 text-sm">
            Already have an account?{" "}
            <button
              onClick={() => navigate("/login")}
              className="text-white font-semibold hover:text-white/80 transition-colors"
            >
              Log in
            </button>
          </p>
        </motion.div>
      </div>
    </main>
  );
}
