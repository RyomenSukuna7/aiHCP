import React from "react";
import LogInteractionForm from "./components/LogInteractionForm";
import ChatPanel from "./components/ChatPanel";
import "./index.css";

export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-title">Log HCP Interaction</span>
      </header>
      <main className="app-body">
        <LogInteractionForm />
        <ChatPanel />
      </main>
    </div>
  );
}
