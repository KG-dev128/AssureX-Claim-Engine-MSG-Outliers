import { Link, useRouterState } from "@tanstack/react-router";
import { ArrowRight, Menu, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";

const nav = [
  { to: "/", label: "Home" },
  { to: "/how-it-works", label: "How It Works" },
  { to: "/support", label: "Support" },
  { to: "/about", label: "About" },
] as const;

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  return <header className="site-header">
    <Link to="/" className="brand" aria-label="AssureX Warranty Claim home" onClick={() => setOpen(false)}><span className="brand-mark"><ShieldCheck size={19} strokeWidth={2.2} /></span><span>AssureX</span></Link>
    <nav className={`main-nav ${open ? "is-open" : ""}`} aria-label="Main navigation">
      {nav.map(item => <Link key={item.to} to={item.to} onClick={() => setOpen(false)} className={`nav-link ${pathname === item.to ? "active" : ""}`}>{item.label}</Link>)}
      <Link to="/track" onClick={() => setOpen(false)} className={`nav-link nav-track ${pathname === "/track" ? "active" : ""}`}>Track Device</Link>
    </nav>
    <div className="header-actions"><Button asChild variant="pill" size="sm"><Link to="/signup">Get Started <ArrowRight size={14} /></Link></Button></div>
    <Button variant="ghost" size="icon" className="menu-toggle" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} onClick={() => setOpen(!open)}>{open ? <X /> : <Menu />}</Button>
  </header>;
}

export function SiteFooter() {
  return <footer className="site-footer"><div className="footer-top"><div><Link to="/" className="brand footer-brand"><span className="brand-mark"><ShieldCheck size={19} strokeWidth={2.2} /></span><span>AssureX Warranty Claim</span></Link><p>Your Device. Your Warranty. Our Assurance.</p></div><nav aria-label="Footer navigation"><Link to="/">Home</Link><Link to="/how-it-works">How It Works</Link><Link to="/support">Support</Link><Link to="/about">About</Link><Link to="/faq">FAQ</Link></nav></div><div className="footer-bottom"><span>© {new Date().getFullYear()} AssureX Warranty Claim. All rights reserved.</span><span>Manage your warranty with confidence.</span></div></footer>;
}
