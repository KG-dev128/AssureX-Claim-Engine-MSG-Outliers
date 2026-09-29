import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/page-parts";
import hero from "@/assets/mascot-hero.jpg";
export const Route = createFileRoute("/faq")({head:()=>({meta:[{title:"Frequently Asked Questions — AssureX Warranty Claim"},{name:"description",content:"Answers to common questions about AssureX Warranty Claim warranty support, tracking, timing and support."},{property:"og:title",content:"Frequently Asked Questions — AssureX Warranty Claim"},{property:"og:description",content:"Find quick answers to the most common questions."},{property:"og:type",content:"website"},{name:"twitter:card",content:"summary_large_image"}]}),component:FAQ});
const faqs=[
  ["How can I see what my warranty covers?","Add your warranty information to see its coverage, provider, start date, and expiry date in your account."],
  ["What do I need to submit a claim?","Select a registered product, describe the fault, and provide the relevant warranty details and evidence."],
  ["Which documents should I keep?","Not usually. Keep the purchase receipt or invoice, warranty card, product label, and any claim evidence together."],
  ["Can I edit information read from a receipt?","Yes. Review and correct receipt details before you confirm them. OCR is not connected in this preview, so enter the information manually."],
  ["How do I track a submitted claim?","Open My Claims from your dashboard to see the claim ID and recorded status. Live reviewer updates require a connected service."],
  ["Does submitting a claim guarantee approval?","No. A reviewer determines the outcome after assessing the submitted details and evidence."],
];
function FAQ(){return <main className="inner-page faq-page"><section className="page-heading"><Eyebrow>FAQ</Eyebrow><h1>Frequently Asked Questions</h1><p>Find quick answers to the most common questions.</p><span className="scribble">Here to<br/>help! ↝</span></section><div className="faq-list">{faqs.map(([question,answer])=><details key={question}><summary>{question}<ChevronDown size={18}/></summary><p>{answer}</p></details>)}</div><section className="faq-help"><img src={hero} width={1536} height={1024} loading="lazy" alt="AssureX Warranty Claim mascot looking after a phone"/><div><h2>Still have questions?</h2><p>Our support team is happy to help.</p><Button asChild variant="pill"><Link to="/support">Contact us <ArrowRight size={15}/></Link></Button></div></section></main>}
