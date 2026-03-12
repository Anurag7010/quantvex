import React from "react";
import { NavbarHero } from "../components/ui/hero-with-video";
import { useNavigate } from "react-router-dom";

const HomePage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <NavbarHero
      brandName="Finance MCP"
      heroTitle="AI-Driven Market Intelligence"
      heroDescription={
        "Analyze global markets using real-time financial data, supply-chain \nknowledge graphs, and AI-powered reasoning."
      }
      backgroundImage="/earth-bg.png"
      onNavigateChat={() => navigate("/chat")}
      onNavigateDashboard={() => navigate("/dashboard")}
    />
  );
};

export default HomePage;
