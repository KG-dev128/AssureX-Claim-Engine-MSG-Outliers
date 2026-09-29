import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, ArrowUpRight, FileCheck2, HeartHandshake, Leaf, Play, ShieldCheck, Sprout, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/page-parts";
import hero from "@/assets/mascot-hero.jpg";
import workshop from "@/assets/mascot-workshop.jpg";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [
    { title: "AssureX Warranty Claim — Your Device. Your Warranty. Our Assurance." },
    { name: "description", content: "From registration to resolution, AssureX keeps your warranty journey clear, organized, and easy to track." },
    { property: "og:title", content: "AssureX Warranty Claim — Your Device. Your Warranty. Our Assurance." },
    { property: "og:description", content: "Manage your products, warranty documents, and claims with confidence." },
    { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: Home,
});

function Home() {
  return <main>
    <section className="home-hero" style={{ backgroundImage: `url(${hero})` }}>
      <div className="home-hero-content"><Eyebrow>Your Device. Your Warranty. Our Assurance.</Eyebrow><h1>Your warranty,<br/>made clear.</h1><p>From registration to resolution, keep your warranty, documents, and claims organized in one place.</p><div className="hero-actions"><Button asChild variant="pill"><Link to="/signup">Get Started <ArrowRight size={16}/></Link></Button><Button asChild variant="link"><Link to="/how-it-works">How It Works <Play size={15}/></Link></Button></div></div>
    </section>
    <section className="features-grid" aria-label="Why AssureX">{[{icon:ShieldCheck,title:"Warranty clarity",text:"Know what is covered and when it ends."},{icon:FileCheck2,title:"Documents together",text:"Keep receipts and product records close."},{icon:Leaf,title:"A simpler process",text:"Follow your claim one step at a time."},{icon:HeartHandshake,title:"Support when needed",text:"Get help through your warranty journey."}].map(({icon: Icon, title, text}) => <div className="feature" key={title}><div className="feature-icon"><Icon size={21} strokeWidth={1.65}/></div><h2>{title}</h2><p>{text}</p></div>)}</section>
    <section className="home-story"><img src={workshop} width={1536} height={768} loading="lazy" alt="Careful product maintenance in a sunlit workshop"/><div className="story-note">Every detail.<br/>In one place.<ShieldCheck size={24}/></div></section>
    <section className="home-next"><div><Eyebrow>One clear place for your warranty</Eyebrow><h2>Stay in the know.</h2><p>Register a product, keep its documents together, and track every step of a claim.</p></div><Button asChild variant="pill"><Link to="/signup">Create your account <ArrowUpRight size={16}/></Link></Button></section>
    <div className="home-bottom-mark"><Wrench size={16}/> From registration to resolution.</div>
  </main>;
}
