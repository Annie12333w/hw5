// The five agents: names, roles, and their cartoon mascots (inline SVG, no image files).
import type { AgentName } from "./types";

export interface AgentMeta {
  name: AgentName;
  title: string;
  animal: string;
  outfit: string;
  role: string;
  Avatar: (p: { size?: number }) => React.JSX.Element;
}

const NAVY = "#0b1f3a";
const BLUE = "#1f4e8c";
const SKY = "#5b8fd6";
const INK = "#1d2433";

function Eyes({ y = 52, dx = 12, cx = 60 }: { y?: number; dx?: number; cx?: number }) {
  return (
    <g fill={INK}>
      <circle cx={cx - dx} cy={y} r={4} />
      <circle cx={cx + dx} cy={y} r={4} />
      <circle cx={cx - dx + 1.3} cy={y - 1.4} r={1.3} fill="#fff" />
      <circle cx={cx + dx + 1.3} cy={y - 1.4} r={1.3} fill="#fff" />
    </g>
  );
}

/** Boss: a lion in a navy suit and blue tie. */
function Lion({ size = 96 }: { size?: number }) {
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} aria-hidden="true">
      <path d="M22 120 Q24 92 60 90 Q96 92 98 120Z" fill={NAVY} />
      <path d="M50 90 L60 108 L70 90Z" fill="#fff" />
      <path d="M57 92 L63 92 L65 112 L60 118 L55 112Z" fill={SKY} />
      <path d="M50 90 L44 104 L56 98Z M70 90 L76 104 L64 98Z" fill="#14315c" />
      <circle cx="60" cy="52" r="38" fill="#c98a3a" />
      {[0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330].map((a) => (
        <circle key={a} cx={60 + 36 * Math.cos((a * Math.PI) / 180)} cy={52 + 36 * Math.sin((a * Math.PI) / 180)} r={9} fill="#b5762c" />
      ))}
      <circle cx="60" cy="54" r="27" fill="#f2c46d" />
      <circle cx="38" cy="32" r="7" fill="#f2c46d" /><circle cx="82" cy="32" r="7" fill="#f2c46d" />
      <Eyes y={50} dx={10} />
      <ellipse cx="60" cy="66" rx="12" ry="9" fill="#fbe3b0" />
      <path d="M55 61 L65 61 L60 67Z" fill="#7a4a1d" />
      <path d="M60 67 Q56 72 52 70 M60 67 Q64 72 68 70" stroke="#7a4a1d" strokeWidth="1.8" fill="none" strokeLinecap="round" />
    </svg>
  );
}

/** Inventory: a beaver in a hard hat and hi-vis vest, holding a clipboard. */
function Beaver({ size = 96 }: { size?: number }) {
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} aria-hidden="true">
      <path d="M24 120 Q26 92 60 90 Q94 92 96 120Z" fill={BLUE} />
      <path d="M36 98 L36 120 M84 98 L84 120" stroke="#e8eef8" strokeWidth="5" />
      <path d="M26 108 L94 108" stroke="#e8eef8" strokeWidth="4" />
      <rect x="66" y="94" width="22" height="26" rx="3" fill="#f5f7fa" stroke={INK} strokeWidth="1.5" />
      <rect x="72" y="91" width="10" height="5" rx="1.5" fill="#8a919c" />
      <path d="M70 102 H84 M70 107 H84 M70 112 H80" stroke="#8a919c" strokeWidth="1.6" />
      <circle cx="36" cy="40" r="8" fill="#7a4a24" /><circle cx="84" cy="40" r="8" fill="#7a4a24" />
      <ellipse cx="60" cy="58" rx="30" ry="31" fill="#8b5a2b" />
      <ellipse cx="60" cy="70" rx="17" ry="13" fill="#c69462" />
      <Eyes y={54} dx={11} />
      <ellipse cx="60" cy="64" rx="6" ry="4" fill={INK} />
      <rect x="54" y="72" width="5.5" height="9" rx="1.5" fill="#fff" stroke={INK} strokeWidth="0.8" />
      <rect x="60.5" y="72" width="5.5" height="9" rx="1.5" fill="#fff" stroke={INK} strokeWidth="0.8" />
      <path d="M28 36 Q60 4 92 36Z" fill="#f2b705" />
      <rect x="24" y="34" width="72" height="7" rx="3.5" fill="#d99e00" />
      <rect x="56" y="12" width="8" height="22" rx="3" fill="#ffd23f" />
    </svg>
  );
}

/** Accounting: an owl with round glasses, a banker's visor and a calculator. */
function Owl({ size = 96 }: { size?: number }) {
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} aria-hidden="true">
      <path d="M26 120 Q28 90 60 88 Q92 90 94 120Z" fill="#e8eef8" />
      <path d="M52 90 L60 98 L68 90 L68 100 L60 96 L52 100Z" fill={NAVY} />
      <rect x="44" y="102" width="32" height="18" rx="3" fill="#2a3446" />
      <rect x="47" y="104" width="26" height="5" rx="1" fill="#b9d3f5" />
      {[0, 1, 2, 3].map((i) => <rect key={i} x={48 + i * 6.5} y={112} width={4.5} height={4} rx={1} fill="#e2e5ea" />)}
      <path d="M30 30 L40 46 L36 26Z M90 30 L80 46 L84 26Z" fill="#6c7a90" />
      <ellipse cx="60" cy="60" rx="32" ry="32" fill="#8796ad" />
      <ellipse cx="60" cy="68" rx="20" ry="20" fill="#d6dde8" />
      <circle cx="47" cy="56" r="11" fill="#fff" /><circle cx="73" cy="56" r="11" fill="#fff" />
      <circle cx="47" cy="57" r="5" fill={INK} /><circle cx="73" cy="57" r="5" fill={INK} />
      <circle cx="48.5" cy="55.5" r="1.6" fill="#fff" /><circle cx="74.5" cy="55.5" r="1.6" fill="#fff" />
      <circle cx="47" cy="56" r="12.5" fill="none" stroke={NAVY} strokeWidth="2.5" />
      <circle cx="73" cy="56" r="12.5" fill="none" stroke={NAVY} strokeWidth="2.5" />
      <path d="M59.5 56 H60.5" stroke={NAVY} strokeWidth="2.5" />
      <path d="M56 68 L64 68 L60 75Z" fill="#e0a43a" />
      <path d="M28 40 Q60 22 92 40 L86 44 Q60 32 34 44Z" fill={SKY} opacity="0.9" />
      <path d="M30 38 Q60 26 90 38" stroke={BLUE} strokeWidth="3" fill="none" />
    </svg>
  );
}

/** Facilities: a bear in a work cap and overalls with a wrench. */
function Bear({ size = 96 }: { size?: number }) {
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} aria-hidden="true">
      <path d="M24 120 Q26 90 60 88 Q94 90 96 120Z" fill="#a9b4c4" />
      <path d="M38 96 L38 120 L82 120 L82 96 Q60 104 38 96Z" fill={BLUE} />
      <path d="M40 90 L44 100 M80 90 L76 100" stroke={BLUE} strokeWidth="5" strokeLinecap="round" />
      <circle cx="45" cy="101" r="2.5" fill="#ffd23f" /><circle cx="75" cy="101" r="2.5" fill="#ffd23f" />
      <g transform="rotate(-30 86 108)">
        <rect x="84" y="96" width="5" height="22" rx="2" fill="#8a919c" />
        <path d="M80 92 a6 6 0 1 1 13 0 l-3 2 h-7Z" fill="#8a919c" />
      </g>
      <circle cx="34" cy="34" r="11" fill="#6b4226" /><circle cx="86" cy="34" r="11" fill="#6b4226" />
      <circle cx="34" cy="34" r="5" fill="#a87a55" /><circle cx="86" cy="34" r="5" fill="#a87a55" />
      <circle cx="60" cy="58" r="31" fill="#7b4f2e" />
      <ellipse cx="60" cy="70" rx="15" ry="11" fill="#c9a07a" />
      <Eyes y={54} dx={11} />
      <ellipse cx="60" cy="65" rx="5.5" ry="4" fill={INK} />
      <path d="M60 69 Q56 74 52 72 M60 69 Q64 74 68 72" stroke={INK} strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <path d="M32 38 Q60 14 88 38Z" fill={NAVY} />
      <path d="M60 38 L98 40 Q96 45 60 42Z" fill={NAVY} />
      <circle cx="60" cy="24" r="3" fill={SKY} />
    </svg>
  );
}

/** Customer Service: a golden retriever with a headset and a polo shirt. */
function Dog({ size = 96 }: { size?: number }) {
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} aria-hidden="true">
      <path d="M24 120 Q26 90 60 88 Q94 90 96 120Z" fill={SKY} />
      <path d="M50 89 L60 100 L70 89Z" fill="#fff" />
      <circle cx="60" cy="96" r="1.6" fill={NAVY} /><circle cx="60" cy="103" r="1.6" fill={NAVY} />
      <ellipse cx="31" cy="60" rx="10" ry="20" fill="#c98a3a" transform="rotate(12 31 60)" />
      <ellipse cx="89" cy="60" rx="10" ry="20" fill="#c98a3a" transform="rotate(-12 89 60)" />
      <ellipse cx="60" cy="56" rx="28" ry="30" fill="#e6b15c" />
      <ellipse cx="60" cy="72" rx="15" ry="11" fill="#f5d59a" />
      <Eyes y={52} dx={11} />
      <ellipse cx="60" cy="65" rx="6" ry="4.5" fill={INK} />
      <path d="M60 69 Q60 75 55 76 M60 69 Q60 75 65 76" stroke={INK} strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <path d="M56 77 Q60 84 64 77Z" fill="#e8798a" />
      <path d="M30 50 Q30 18 60 18 Q90 18 90 50" stroke={NAVY} strokeWidth="4.5" fill="none" />
      <rect x="24" y="46" width="10" height="16" rx="4" fill={NAVY} />
      <rect x="86" y="46" width="10" height="16" rx="4" fill={NAVY} />
      <path d="M29 60 Q32 80 50 78" stroke={NAVY} strokeWidth="2.5" fill="none" />
      <circle cx="51" cy="78" r="3" fill={NAVY} />
    </svg>
  );
}

export const AGENTS: Record<AgentName, AgentMeta> = {
  boss: { name: "boss", title: "Boss", animal: "Lion", outfit: "navy suit & tie",
          role: "Reads the ticket, routes work, makes the final call", Avatar: Lion },
  inventory: { name: "inventory", title: "Inventory", animal: "Beaver", outfit: "hard hat & clipboard",
               role: "Stock, shortfalls, vendors, lead times", Avatar: Beaver },
  accounting: { name: "accounting", title: "Accounting", animal: "Owl", outfit: "visor, glasses & calculator",
                role: "Cash, invoices, margins, payment requests", Avatar: Owl },
  facilities: { name: "facilities", title: "Facilities", animal: "Bear", outfit: "work cap, overalls & wrench",
                role: "Leases, rent, the shop space", Avatar: Bear },
  customer_service: { name: "customer_service", title: "Customer Service", animal: "Golden retriever",
                      outfit: "headset & polo", role: "Drafts customer messages", Avatar: Dog },
};

export const SPECIALISTS: AgentName[] = ["inventory", "accounting", "facilities", "customer_service"];

export const isAgent = (a: string | null | undefined): a is AgentName => !!a && a in AGENTS;

export const agentTitle = (a: string | null | undefined) =>
  isAgent(a) ? AGENTS[a].title : a === "human" ? "You" : a === "system" ? "System" : (a ?? "");
