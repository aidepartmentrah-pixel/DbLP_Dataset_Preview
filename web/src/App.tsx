import { NavLink, Route, Routes } from "react-router-dom";

import { useTheme } from "./lib/useTheme";
import Author from "./pages/Author";
import Chat from "./pages/Chat";
import Dashboard from "./pages/Dashboard";
import GraphExplorer from "./pages/GraphExplorer";
import Rankings from "./pages/Rankings";

const links = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/graph", label: "Graph" },
  { to: "/rankings", label: "Rankings" },
  { to: "/chat", label: "Chat" },
];

export default function App() {
  const [theme, toggleTheme] = useTheme();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>DBLP Explorer</h1>
        <nav>
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => (isActive ? "active" : "")}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <button className="theme-toggle" onClick={toggleTheme}>
          {theme === "light" ? "Dark mode" : "Light mode"}
        </button>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/graph" element={<GraphExplorer />} />
          <Route path="/rankings" element={<Rankings />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/author/:authorId" element={<Author />} />
        </Routes>
      </main>
    </div>
  );
}
