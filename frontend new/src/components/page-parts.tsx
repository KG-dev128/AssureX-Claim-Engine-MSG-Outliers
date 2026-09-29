import { Link } from "@tanstack/react-router";
import { ArrowRight, Sprout } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Eyebrow({ children }: { children: React.ReactNode }) { return <div className="eyebrow">{children}</div>; }
export function CareCta({ title = "Still need help?", text = "Our support team is always happy to help.", label = "Contact us" }: { title?: string; text?: string; label?: string }) {
  return <div className="care-cta"><div className="care-cta-icon"><Sprout size={28} /></div><div><strong>{title}</strong><p>{text}</p></div><Button asChild variant="outlineLight" size="sm"><Link to="/support">{label} <ArrowRight size={15}/></Link></Button></div>;
}
