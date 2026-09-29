import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, ClipboardCheck, SearchCheck, ShieldCheck, Sparkles, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CareCta, Eyebrow } from "@/components/page-parts";
import workshop from "@/assets/mascot-workshop.jpg";
import hero from "@/assets/mascot-hero.jpg";
export const Route = createFileRoute("/how-it-works")({ head: () => ({meta: [{title:"How It Works — AssureX Warranty Claim"},{name:"description",content:"See how AssureX Warranty Claim takes your device from concern to care in five simple steps."},{property:"og:title",content:"How It Works — AssureX Warranty Claim"},{property:"og:description",content:"From registration to resolution, one step at a time."},{property:"og:type",content:"website"},{name:"twitter:card",content:"summary_large_image"}]}), component: HowItWorks });
const steps = [
  {number:"01", icon: ClipboardCheck, title:"Submitted", text:"Register a product and share the details of its fault.", image: hero},
  {number:"02", icon: SearchCheck, title:"Reviewing", text:"Your submitted information is available for claim review.", image: workshop},
  {number:"03", icon: ShieldCheck, title:"Verified", text:"Keep your warranty and supporting documents together.", image: hero},
  {number:"04", icon: Wrench, title:"Approved", text:"A reviewer determines the claim outcome; no decision is automated.", image: workshop},
  {number:"05", icon: Sparkles, title:"Completed", text:"Follow updates and next steps from your claim timeline.", image: hero},
];
function HowItWorks(){return <main className="inner-page steps-page"><section className="page-heading"><Eyebrow>The journey</Eyebrow><h1>How It Works</h1><p>From registration to resolution, one step at a time.</p><span className="scribble">Same device.<br/>A different story. ↝</span></section><div className="steps-list">{steps.map((step,index)=><article className={`step-row ${index%2 ? "reverse" : ""}`} key={step.number}><div className="step-image"><img src={step.image} width={1536} height={index%2 ? 768 : 1024} loading="lazy" alt={`${step.title} stage of warranty support`}/></div><div className="step-copy"><span className="step-number">{step.number}</span><step.icon size={22} strokeWidth={1.6}/><div><h2>{step.title}</h2><p>{step.text}</p></div></div></article>)}</div><CareCta title="Ready to begin?" text="Your device is in good hands." label="Get in touch"/><div className="steps-bottom"><Button asChild variant="pill"><Link to="/get-started">Create an account <ArrowRight size={16}/></Link></Button></div></main>}
