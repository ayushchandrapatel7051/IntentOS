import React from "react";
import { FontAwesomeIcon as I } from "@fortawesome/react-fontawesome";
import {
  faBolt,
  faTerminal,
  faGlobe,
  faMessage,
  faFolderOpen,
  faBrain,
  faServer,
  faShieldHalved,
  faCodeBranch,
} from "@fortawesome/free-solid-svg-icons";

export function WalkthroughTab() {
  return (
    <div className="walkthrough-container" style={styles.container}>
      <div style={styles.hero}>
        <div style={styles.heroBadge}>DOCUMENTATION</div>
        <h1 style={styles.heroTitle}>IntentOS <span style={styles.accent}>Project Walkthrough</span></h1>
        <p style={styles.heroSubtitle}>
          An Intent-Based Operating System — control your entire computer with natural language.
        </p>
      </div>

      <div style={styles.content}>
        {/* --- Problem Statement --- */}
        <section style={styles.section}>
          <div style={styles.sectionHeader}>
            <div style={styles.sectionIcon}><I icon={faCodeBranch} /></div>
            <h2>Problem Statement</h2>
          </div>
          <div style={styles.card}>
            <p style={styles.text}>
              Modern computer workflows are fragmented, inefficient, and heavily dependent on manual interaction. Users constantly switch between applications, browser tabs, files, messaging platforms, and terminals to complete even simple tasks. A large portion of time is spent not on actual work, but on navigating interfaces, searching for information, opening tools, and repeating routine actions.
            </p>
            <p style={styles.text}>
              Despite advancements in AI, current assistants remain limited to generating responses within chat interfaces. They lack the ability to understand user intent and execute real workflows across the computer environment.
            </p>
            
            <div style={styles.listBlock}>
              <div style={styles.listItem}>
                <span style={styles.listBullet}>•</span>
                <strong>Students</strong> manually manage PDFs, notes, assignments, and online meetings across different platforms.
              </div>
              <div style={styles.listItem}>
                <span style={styles.listBullet}>•</span>
                <strong>Professionals</strong> continuously switch between emails, calendars, documents, and communication tools.
              </div>
              <div style={styles.listItem}>
                <span style={styles.listBullet}>•</span>
                <strong>Developers</strong> repeat workflows such as opening projects, running commands, searching documentation, and managing browser tabs.
              </div>
            </div>

            <div style={styles.warningBox}>
              <I icon={faBolt} style={{ color: "var(--warn)", marginRight: 10 }} />
              Research shows that knowledge workers switch between applications hundreds of times each day, leading to significant productivity loss due to context switching and navigation overhead.
            </div>
            <p style={styles.text}>
              There is currently no unified AI system capable of seamlessly understanding user goals and autonomously executing tasks across applications, files, browsers, and operating system workflows.
            </p>
          </div>
        </section>

        {/* --- Current Solutions --- */}
        <section style={styles.section}>
          <div style={styles.sectionHeader}>
            <div style={styles.sectionIcon}><I icon={faServer} /></div>
            <h2>Current Solutions & Limitations</h2>
          </div>
          <div style={styles.grid}>
            <div style={styles.cardSmall}>
              <h3 style={styles.cardTitle}>Voice Assistants</h3>
              <p style={styles.textSmall}>Cortana, Siri, and Alexa can answer questions and set reminders, but they cannot execute complex workflows across a user’s computer.</p>
            </div>
            <div style={styles.cardSmall}>
              <h3 style={styles.cardTitle}>Conversational AI</h3>
              <p style={styles.textSmall}>ChatGPT and desktop copilots provide intelligent responses, yet they still cannot directly interact with applications, files, or local terminals.</p>
            </div>
            <div style={styles.cardSmall}>
              <h3 style={styles.cardTitle}>Automation Platforms</h3>
              <p style={styles.textSmall}>Zapier and Make.com depend heavily on pre-configured rules, APIs, and manual setup rather than understanding natural language intent.</p>
            </div>
            <div style={styles.cardSmall}>
              <h3 style={styles.cardTitle}>Browser Agents</h3>
              <p style={styles.textSmall}>Restricted mainly to browser environments and cannot effectively control native desktop applications or local files.</p>
            </div>
          </div>
          <div style={{ ...styles.card, marginTop: 16 }}>
            <p style={styles.text}>
              A major gap in existing systems is that each solution addresses only one part of the workflow instead of providing an integrated operating layer across the computer. They lack persistent memory and contextual learning, meaning every execution starts from scratch without improving from previous interactions. Additionally, there is little fault tolerance or rollback capability.
            </p>
          </div>
        </section>

        {/* --- Our Solution --- */}
        <section style={styles.section}>
          <div style={styles.sectionHeader}>
            <div style={{ ...styles.sectionIcon, background: "rgba(0, 212, 170, 0.1)", color: "var(--accent)" }}><I icon={faBolt} /></div>
            <h2 style={{ color: "var(--accent)" }}>Our Solution: IntentOS</h2>
          </div>
          <div style={styles.card}>
            <p style={styles.text}>
              <strong>IntentOS</strong> is an intent-driven AI operating layer designed to help users control their computers using natural language. Instead of manually switching between applications, browsers, files, terminals, and messaging platforms, users simply describe what they want to accomplish, and the system autonomously executes the workflow.
            </p>
            <p style={styles.text}>
              The platform combines AI reasoning, browser automation, desktop control, workflow memory, and recovery mechanisms into a single unified execution system.
            </p>
            
            <h3 style={{...styles.cardTitle, marginTop: 24, marginBottom: 12}}>How Work is Done (The 4 Core Components)</h3>
            <div style={styles.componentSteps}>
              
              <div style={styles.compStep}>
                <div style={styles.compStepNum}>1</div>
                <div style={styles.compStepContent}>
                  <h4>The Planner</h4>
                  <p>Analyzes user intent and breaks complex requests into smaller executable JSON actions using Gemini 2.5 Flash.</p>
                </div>
              </div>

              <div style={styles.compStep}>
                <div style={styles.compStepNum}>2</div>
                <div style={styles.compStepContent}>
                  <h4>The Executor</h4>
                  <p>Routes and performs these actions across browsers, files, terminals, messaging platforms, and AI modules.</p>
                </div>
              </div>

              <div style={styles.compStep}>
                <div style={styles.compStepNum}>3</div>
                <div style={styles.compStepContent}>
                  <h4>Memory & Recovery</h4>
                  <p>Stores successful workflows in ChromaDB, enabling faster execution, intelligent recovery, and automatic replanning if failures occur.</p>
                </div>
              </div>

              <div style={styles.compStep}>
                <div style={styles.compStepNum}>4</div>
                <div style={styles.compStepContent}>
                  <h4>Macros System</h4>
                  <p>Allows users to save reusable workflows to `SOUL.md`, enabling instant execution of repetitive tasks without repeated prompting or LLM cost.</p>
                </div>
              </div>

            </div>
          </div>
        </section>

        {/* --- Architecture Modules --- */}
        <section style={styles.section}>
          <div style={styles.sectionHeader}>
            <div style={styles.sectionIcon}><I icon={faBrain} /></div>
            <h2>Unified Control Modules</h2>
          </div>
          
          <div style={styles.moduleGrid}>
            <div style={styles.moduleCard}>
              <div style={styles.moduleIcon}><I icon={faTerminal} /></div>
              <h4>Terminal Control</h4>
              <p>Executes PowerShell commands directly on the host, runs scripts, installs packages, and manages the local environment.</p>
            </div>
            
            <div style={styles.moduleCard}>
              <div style={styles.moduleIcon}><I icon={faGlobe} /></div>
              <h4>Browser Automation</h4>
              <p>Navigates pages, extracts text via fast server-side HTML scraping, or fully automates clicks and forms via Chrome Extension MV3 bridge.</p>
            </div>

            <div style={styles.moduleCard}>
              <div style={styles.moduleIcon}><I icon={faFolderOpen} /></div>
              <h4>File Management</h4>
              <p>Universal document extraction (PDF, DOCX, XLSX, Images), edits code, and navigates directories seamlessly.</p>
            </div>

            <div style={styles.moduleCard}>
              <div style={styles.moduleIcon}><I icon={faMessage} /></div>
              <h4>Messaging Integration</h4>
              <p>Automates WhatsApp messaging natively via background execution without requiring manual confirmation gates.</p>
            </div>

            <div style={styles.moduleCard}>
              <div style={styles.moduleIcon}><I icon={faBrain} /></div>
              <h4>Neural Workflow Memory</h4>
              <p>Learns from successful workflows. Before generating new plans, it checks ChromaDB for similar past intents to save time and reduce errors.</p>
            </div>

            <div style={styles.moduleCard}>
              <div style={styles.moduleIcon}><I icon={faShieldHalved} /></div>
              <h4>Safety Guardrails</h4>
              <p>Blocks destructive commands (`rm -rf`, `format`) and requires human approval before executing any potentially risky action.</p>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}

const styles = {
  container: {
    padding: "40px",
    overflowY: "auto",
    height: "100%",
    backgroundColor: "var(--bg)",
    color: "var(--text)",
  },
  hero: {
    marginBottom: "48px",
    borderBottom: "1px solid var(--border2)",
    paddingBottom: "32px",
  },
  heroBadge: {
    display: "inline-block",
    padding: "4px 8px",
    backgroundColor: "rgba(124, 111, 255, 0.1)",
    color: "var(--accent2)",
    fontFamily: "var(--mono)",
    fontSize: "10px",
    letterSpacing: "1px",
    borderRadius: "4px",
    marginBottom: "16px",
  },
  heroTitle: {
    fontFamily: "var(--ui)",
    fontSize: "36px",
    fontWeight: "600",
    marginBottom: "12px",
  },
  accent: {
    color: "var(--accent)",
  },
  heroSubtitle: {
    fontFamily: "var(--mono)",
    fontSize: "14px",
    color: "var(--muted)",
    maxWidth: "600px",
    lineHeight: "1.6",
  },
  content: {
    display: "flex",
    flexDirection: "column",
    gap: "40px",
    maxWidth: "900px",
  },
  section: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
  },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  sectionIcon: {
    width: "32px",
    height: "32px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "var(--surface2)",
    borderRadius: "8px",
    color: "var(--text)",
    fontSize: "14px",
  },
  card: {
    backgroundColor: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "12px",
    padding: "24px",
    boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: "16px",
  },
  cardSmall: {
    backgroundColor: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "8px",
    padding: "16px",
  },
  cardTitle: {
    fontSize: "14px",
    fontWeight: "600",
    marginBottom: "8px",
    fontFamily: "var(--ui)",
    color: "var(--text)",
  },
  text: {
    fontSize: "14px",
    lineHeight: "1.7",
    color: "var(--text)",
    marginBottom: "16px",
  },
  textSmall: {
    fontSize: "13px",
    lineHeight: "1.6",
    color: "var(--muted)",
  },
  listBlock: {
    margin: "16px 0",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    paddingLeft: "8px",
  },
  listItem: {
    display: "flex",
    alignItems: "flex-start",
    gap: "12px",
    fontSize: "14px",
    lineHeight: "1.6",
    color: "var(--text)",
  },
  listBullet: {
    color: "var(--accent)",
    fontWeight: "bold",
  },
  warningBox: {
    display: "flex",
    alignItems: "flex-start",
    backgroundColor: "rgba(245, 158, 11, 0.05)",
    border: "1px solid rgba(245, 158, 11, 0.2)",
    borderRadius: "6px",
    padding: "16px",
    margin: "24px 0",
    fontSize: "13px",
    fontFamily: "var(--mono)",
    color: "var(--text)",
    lineHeight: "1.5",
  },
  componentSteps: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
  },
  compStep: {
    display: "flex",
    gap: "16px",
    backgroundColor: "var(--surface2)",
    padding: "16px",
    borderRadius: "8px",
    borderLeft: "2px solid var(--accent)",
  },
  compStepNum: {
    fontFamily: "var(--mono)",
    fontSize: "20px",
    fontWeight: "bold",
    color: "var(--accent)",
    width: "24px",
  },
  compStepContent: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  moduleGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))",
    gap: "16px",
  },
  moduleCard: {
    backgroundColor: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: "12px",
    padding: "20px",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    transition: "transform 0.2s, border-color 0.2s",
  },
  moduleIcon: {
    width: "40px",
    height: "40px",
    borderRadius: "8px",
    backgroundColor: "rgba(255,255,255,0.03)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "var(--accent2)",
    fontSize: "18px",
  },
};
