import { useEffect } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import Nav from "./components/layout/Nav";
import Footer from "./components/layout/Footer";
import Stub from "./components/layout/Stub";
import SmoothScroll from "./motion/SmoothScroll";
import { useReducedMotion } from "./motion/useReducedMotion";
import { EASE } from "./motion/easing";
import Landing from "./pages/Landing";
import Scan from "./pages/Scan";
import ReportPage from "./pages/Report";
import Dashboard from "./pages/Dashboard";
import History from "./pages/History";
import About from "./pages/About";
import Docs from "./pages/Docs";
import Interactions from "./components/layout/Interactions";

function Shell() {
  const { pathname } = useLocation();
  const reduced = useReducedMotion();
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <Nav />
      <motion.main id="main" key={pathname} initial={reduced ? false : { opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: EASE }}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/scan" element={<Scan />} />
          <Route path="/scan/:mode" element={<Scan />} />
          <Route path="/report/:id" element={<ReportPage />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/history" element={<History />} />
          <Route path="/about" element={<About />} />
          <Route path="/docs" element={<Docs />} />
          <Route path="/extension" element={<Stub title="Install the extension" note="Later step." />} />
          <Route path="*" element={<Stub title="Not found" note="That page does not exist." />} />
        </Routes>
      </motion.main>
      <Footer />
    </>
  );
}
export default function App() {
  return <BrowserRouter><SmoothScroll /><Interactions /><Shell /></BrowserRouter>;
}