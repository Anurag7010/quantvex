import React from "react";
import { Hero } from "../components/ui/animated-hero";
import { useNavigate } from "react-router-dom";

const HomePage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <Hero
      onNavigateAnalysis={() => navigate("/chat")}
      onNavigateDashboard={() => navigate("/dashboard")}
    />
  );
};

export default HomePage;
