import React from "react";
import { NavbarHero } from "../components/ui/hero-with-video";
import { useNavigate } from "react-router-dom";

const HomePage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <NavbarHero
      brandName="Finance MCP"
      heroTitle="Market Intelligence, Engineered for Perfection"
      heroDescription={
        "A unified system for real-time market data,supply chain dependency analysis,\nand multi-agent financial reasoning."
      }
      onNavigateChat={() => navigate("/chat")}
      onNavigateDashboard={() => navigate("/dashboard")}
    />
  );
};

export default HomePage;
