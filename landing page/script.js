/* MODELRAIL — Platform Interactions & Visualizations */
(() => {
	const reduceMotion = window.matchMedia(
		"(prefers-reduced-motion: reduce)",
	).matches;
	const $ = (s, c = document) => c.querySelector(s);
	const $$ = (s, c = document) => Array.from(c.querySelectorAll(s));

	/* ---------- Header scroll state ---------- */
	const header = $("#header");
	const onScroll = () =>
		header.classList.toggle("scrolled", window.scrollY > 40);
	onScroll();
	window.addEventListener("scroll", onScroll, { passive: true });

	/* ---------- Location-Aware Live Clock (Spec §nav) ---------- */
	const clockEl = $("#clock-time");
	const clockLocEl = $("#clock-location");

	function getTzAbbr() {
		try {
			return (
				new Intl.DateTimeFormat("en-US", { timeZoneName: "short" })
					.formatToParts(new Date())
					.find((p) => p.type === "timeZoneName")?.value || ""
			);
		} catch (_e) {
			return "";
		}
	}

	function renderLocation(text) {
		if (!clockLocEl) return;
		const txtEl = clockLocEl.querySelector(".loc-txt");
		if (txtEl) {
			txtEl.textContent = text;
		} else {
			clockLocEl.innerHTML = `<span class="live-dot" aria-hidden="true"></span><span class="loc-txt">${text}</span>`;
		}
	}

	// 1. Instant client-side location & timezone from browser (0ms latency, 100% reliable)
	const tzAbbr = getTzAbbr();
	let detectedTz = "UTC";
	try {
		detectedTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
		const parts = detectedTz.split("/");
		const cityFromTz = (parts[parts.length - 1] || "LOCAL").replace(/_/g, " ").toUpperCase();
		const initialLabel = tzAbbr ? `${cityFromTz} · ${tzAbbr}` : cityFromTz;
		renderLocation(initialLabel);
	} catch (_e) {
		renderLocation("LOCAL TIME");
	}

	// 2. Refine with IP geolocation asynchronously (non-blocking)
	function refineLocationViaIp() {
		try {
			const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
			const timeoutId = controller ? setTimeout(() => controller.abort(), 4000) : null;
			fetch("https://ipapi.co/json/", { signal: controller ? controller.signal : undefined })
				.then((res) => {
					if (timeoutId) clearTimeout(timeoutId);
					if (!res.ok) throw new Error("HTTP " + res.status);
					return res.json();
				})
				.then((data) => {
					if (data && data.city) {
						const city = data.city.toUpperCase();
						const country = data.country_code ? `, ${data.country_code}` : "";
						const zone = data.utc_offset || tzAbbr;
						renderLocation(`${city}${country} · ${zone}`);
					}
				})
				.catch(() => {
					// Fallback to secondary IP geolocation provider if primary is rate-limited
					fetch("https://ipwho.is/")
						.then((r) => r.json())
						.then((data) => {
							if (data && data.success && data.city) {
								const city = data.city.toUpperCase();
								const country = data.country_code ? `, ${data.country_code}` : "";
								renderLocation(`${city}${country} · ${tzAbbr}`);
							}
						})
						.catch(() => {
							// Retain the Intl timezone city
						});
				});
		} catch (_e) {
			// Retain initial client detection
		}
	}

	if (typeof window !== "undefined" && window.fetch) {
		setTimeout(refineLocationViaIp, 100);
	}

	function tick() {
		try {
			clockEl.textContent = new Intl.DateTimeFormat("en-US", {
				hour: "2-digit",
				minute: "2-digit",
				second: "2-digit",
				hour12: false,
			}).format(new Date());
		} catch (_e) {
			clockEl.textContent = new Date().toTimeString().slice(0, 8);
		}
	}
	tick();
	setInterval(tick, 1000);

	/* ---------- Solutions/System dropdown ---------- */
	const menuBtn = $("#menu-btn"),
		dropdown = $("#dropdown");
	function closeMenu() {
		dropdown.classList.remove("open");
		menuBtn.classList.remove("open");
		menuBtn.setAttribute("aria-expanded", "false");
	}
	menuBtn.addEventListener("click", (e) => {
		e.stopPropagation();
		const open = dropdown.classList.toggle("open");
		menuBtn.classList.toggle("open", open);
		menuBtn.setAttribute("aria-expanded", String(open));
	});
	document.addEventListener("click", (e) => {
		if (!dropdown.contains(e.target) && !menuBtn.contains(e.target))
			closeMenu();
	});
	document.addEventListener("keydown", (e) => {
		if (e.key === "Escape") closeMenu();
	});
	$$("#dropdown a").forEach((a) => a.addEventListener("click", closeMenu));

	/* ---------- Scroll reveal ---------- */
	const io = new IntersectionObserver(
		(entries) => {
			entries.forEach((en) => {
				if (en.isIntersecting) {
					en.target.classList.add("in");
					const m = en.target.querySelector(".mask");
					if (m) m.classList.add("in");
					io.unobserve(en.target);
				}
			});
		},
		{ threshold: 0.14, rootMargin: "0px 0px -40px 0px" },
	);
	$$(".reveal").forEach((el) => io.observe(el));

	/* ---------- Count-up metrics ---------- */
	const counters = $$("[data-count]");
	const cio = new IntersectionObserver(
		(entries) => {
			entries.forEach((en) => {
				if (!en.isIntersecting) return;
				const el = en.target;
				cio.unobserve(el);
				const target = parseFloat(el.dataset.count);
				const dec = parseInt(el.dataset.dec || "0", 10);
				if (reduceMotion) {
					el.textContent = target.toFixed(dec);
					return;
				}
				const dur = 1200,
					t0 = performance.now();
				function step(now) {
					const p = Math.min((now - t0) / dur, 1);
					const eased = 1 - (1 - p) ** 3;
					el.textContent = (target * eased).toFixed(dec);
					if (p < 1) requestAnimationFrame(step);
					else el.textContent = target.toFixed(dec);
				}
				requestAnimationFrame(step);
			});
		},
		{ threshold: 0.4 },
	);
	counters.forEach((c) => cio.observe(c));

	/* ---------- Accordions (capabilities & faq) ---------- */
	function wireAccordion(rootSel, itemSel, contentSel) {
		const root = $(rootSel);
		if (!root) return;
		const items = $$(itemSel, root);
		items.forEach((item) => {
			const btn = item.querySelector("button");
			if (!btn) return;
			btn.addEventListener("click", () => {
				const content = item.querySelector(contentSel);
				const isOpen = item.classList.contains("open");
				items.forEach((o) => {
					o.classList.remove("open");
					const c = o.querySelector(contentSel);
					if (c) c.style.maxHeight = null;
				});
				if (!isOpen && content) {
					item.classList.add("open");
					content.style.maxHeight = `${content.scrollHeight}px`;
				}
			});
		});
	}
	wireAccordion("#acc", ".acc-item", ".acc-content");
	wireAccordion("#faq-list", ".faq-q", ".faq-ans");

	/* ---------- Deployment model toggles ---------- */
	const pricing = {
		retainer: {
			off: false,
			on: { amt: "$0", per: "/ forever", cap: "Deterministic Mock Provider" },
			alt: { amt: "$0", per: "/ forever", cap: "Local Ollama Llama-3.1" },
		},
		sprint: {
			off: false,
			on: { amt: "100%", per: "/ self-hosted", cap: "Standard Gateway Stack" },
			alt: { amt: "100%", per: "/ self-hosted", cap: "Full Multi-Worker Cluster" },
		},
		mandate: {
			off: false,
			on: { amt: "GATE", cap: "Dev Benchmark Split (70/30)" },
			alt: { amt: "GATE", cap: "Held-Out Verification Split" },
		},
	};
	$$(".knob[data-toggle]").forEach((knob) => {
		const key = knob.dataset.toggle;
		knob.addEventListener("click", () => {
			const cfg = pricing[key];
			if (!cfg) return;
			cfg.off = !cfg.off;
			knob.classList.toggle("on", cfg.off);
			const data = cfg.off ? cfg.alt : cfg.on;
			const amtEl = $(`#${key}-amt`);
			if (amtEl) amtEl.textContent = data.amt;
			const perEl = $(`#${key}-per`);
			if (perEl && data.per) perEl.textContent = data.per;
			const capEl = $(`#${key}-cap`);
			if (capEl && data.cap) capEl.textContent = data.cap;
			const onLbl = $(`[data-on="${key}"]`),
				offLbl = $(`[data-off="${key}"]`);
			if (onLbl && offLbl) {
				onLbl.classList.toggle("t-off", cfg.off);
				onLbl.classList.toggle("t-on", !cfg.off);
				offLbl.classList.toggle("t-on", cfg.off);
				offLbl.classList.toggle("t-off", !cfg.off);
			}
		});
	});

	/* ---------- Marquee build ---------- */
	const ticks = [
		["MODELRAIL-FAST", "ROUTE: MOCK-1 / OLLAMA", "up"],
		["CIRCUIT BREAKER", "STATE: CLOSED (HEALTHY)", "up"],
		["BUDGET 2-PHASE", "ZERO OVER-ALLOCATION", "neu"],
		["OPENAI COMPAT", "/v1/chat/completions", "up"],
		["RETRY WITH JITTER", "0 DUPLICATE USAGE", "up"],
		["EVAL REGRESSION GATE", "BLOCKED ON >5% DROP", "neu"],
		["P95 OVERHEAD", "< 24.8 MS", "up"],
		["TENANT ISOLATION", "ORG / PROJECT ENFORCED", "neu"],
		["TEST SUITE", "183 PASSING", "up"],
		["OTEL TRACING", "TEMPO CORRELATED", "up"],
		["LOCAL-FIRST", "100% ZERO CLOUD BILL", "up"],
		["OLLAMA ADAPTER", "LLAMA 3.1 NATIVE", "neu"],
	];
	const marquee = $("#marquee");
	if (marquee) {
		const build = () =>
			ticks
				.map(
					([a, b, c]) =>
						`<span class="tick"><span>${a}</span><span class="${c}">${b}</span></span>`,
				)
				.join("");
		marquee.innerHTML = build() + build();
	}

	/* ---------- Sparkline (hero ticker card) ---------- */
	const spark = $("#spark");
	function genPath(w, h, n, jitter) {
		const pts = [];
		let v = h * 0.55;
		for (let i = 0; i < n; i++) {
			v += (Math.random() - 0.48) * jitter;
			v = Math.max(h * 0.2, Math.min(h * 0.8, v));
			pts.push([(i / (n - 1)) * w, v]);
		}
		return pts;
	}
	function drawSpark() {
		if (!spark) return;
		const w = 280,
			h = 88,
			n = 28;
		const pts = genPath(w, h, n, 8);
		const line = pts
			.map((p, i) => `${(i ? "L" : "M") + p[0].toFixed(1)} ${p[1].toFixed(1)}`)
			.join(" ");
		const area = `${line} L${w} ${h} L0 ${h} Z`;
		spark.innerHTML =
			`<path d="${area}" fill="rgba(31,68,255,0.08)"/>` +
			`<path d="${line}" fill="none" stroke="#1f44ff" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>` +
			`<circle cx="${w}" cy="${pts[n - 1][1].toFixed(1)}" r="3.2" fill="#1f44ff"/>`;
	}
	drawSpark();

	/* ---------- Rotating ticker metric ---------- */
	const metrics = [
		["0.00<em>%</em>", "Duplicate Tokens on Retries"],
		["&lt; 24.8<em>ms</em>", "P95 Route & Auth Overhead"],
		["100<em>%</em>", "Budget Concurrency Precision"],
		["3-State", "Circuit Breaker (Closed/Open/Half)"],
	];
	const tcVal = $("#tc-val"),
		tcLab = $("#tc-lab");
	let mi = 0;
	if (!reduceMotion && tcVal && tcLab) {
		setInterval(() => {
			mi = (mi + 1) % metrics.length;
			tcVal.style.opacity = "0";
			tcLab.style.opacity = "0";
			setTimeout(() => {
				tcVal.innerHTML = metrics[mi][0];
				tcLab.textContent = metrics[mi][1];
				drawSpark();
				tcVal.style.opacity = "1";
				tcLab.style.opacity = "1";
			}, 320);
		}, 3800);
		[tcVal, tcLab].forEach((e) => {
			e.style.transition = "opacity 0.3s";
		});
	}

	/* ---------- Reliability Proof SVGs ---------- */
	function drawViz1() {
		const svg = $("#viz1");
		if (!svg) return;
		const W = 400,
			H = 250;
		// Simulated Circuit Breaker: Primary Mock 503 spike -> Breaker Trips -> Fallback activates
		svg.innerHTML = `
			<rect width="${W}" height="${H}" fill="#fbfaf6"/>
			<!-- Background Grid -->
			<line x1="20" y1="50" x2="380" y2="50" stroke="rgba(17,17,20,0.06)" stroke-dasharray="2 2"/>
			<line x1="20" y1="125" x2="380" y2="125" stroke="rgba(17,17,20,0.06)" stroke-dasharray="2 2"/>
			<line x1="20" y1="200" x2="380" y2="200" stroke="rgba(17,17,20,0.06)"/>
			
			<!-- Healthy baseline requests -->
			<rect x="30" y="160" width="12" height="40" fill="rgba(31,68,255,0.7)"/>
			<rect x="50" y="150" width="12" height="50" fill="rgba(31,68,255,0.7)"/>
			<rect x="70" y="155" width="12" height="45" fill="rgba(31,68,255,0.7)"/>
			
			<!-- Injected 503 Outage Spikes -->
			<rect x="95" y="80" width="12" height="120" fill="#ff4d4d"/>
			<rect x="115" y="60" width="12" height="140" fill="#ff4d4d"/>
			<rect x="135" y="45" width="12" height="155" fill="#ff4d4d"/>
			
			<!-- Circuit Trips Line -->
			<line x1="160" y1="25" x2="160" y2="215" stroke="#ff4d4d" stroke-width="1.5" stroke-dasharray="4 3"/>
			<text x="166" y="40" font-family="'JetBrains Mono', monospace" font-size="9" fill="#ff4d4d" font-weight="600">BREAKER: OPEN</text>
			
			<!-- Instant Fallback Traffic Reroute (100% Success) -->
			<rect x="180" y="140" width="14" height="60" fill="#18a957"/>
			<rect x="202" y="145" width="14" height="55" fill="#18a957"/>
			<rect x="224" y="135" width="14" height="65" fill="#18a957"/>
			<rect x="246" y="140" width="14" height="60" fill="#18a957"/>
			<rect x="268" y="138" width="14" height="62" fill="#18a957"/>
			<rect x="290" y="142" width="14" height="58" fill="#18a957"/>
			<rect x="312" y="140" width="14" height="60" fill="#18a957"/>
			<rect x="334" y="145" width="14" height="55" fill="#18a957"/>
			<rect x="356" y="139" width="14" height="61" fill="#18a957"/>
			
			<!-- Labels -->
			<text x="30" y="222" font-family="'JetBrains Mono', monospace" font-size="9" fill="#6b6a66">PRIMARY (200 OK)</text>
			<text x="95" y="32" font-family="'JetBrains Mono', monospace" font-size="9" fill="#ff4d4d">3x 503 FAILS</text>
			<text x="210" y="125" font-family="'JetBrains Mono', monospace" font-size="9" fill="#18a957" font-weight="600">STANDBY ROUTE: 100% HEALTHY</text>
		`;
	}

	function drawViz2() {
		const svg = $("#viz2");
		if (!svg) return;
		const W = 400,
			H = 250;
		// Simulated Concurrency: 50 requests competing for $0.05 budget ceiling
		let bars = "";
		for (let i = 0; i < 36; i++) {
			const x = 25 + i * 9.6;
			if (i < 22) {
				// Accepted & reserved within budget
				const h = 40 + (i % 5) * 8;
				bars += `<rect x="${x.toFixed(1)}" y="${(195 - h).toFixed(1)}" width="6.5" height="${h}" fill="#1f44ff"/>`;
			} else {
				// Rejected with 429 budget_exceeded
				bars += `<rect x="${x.toFixed(1)}" y="185" width="6.5" height="10" fill="rgba(255,77,77,0.85)"/>`;
			}
		}
		svg.innerHTML = `
			<rect width="${W}" height="${H}" fill="#fbfaf6"/>
			<!-- Background Grid -->
			<line x1="20" y1="195" x2="380" y2="195" stroke="rgba(17,17,20,0.12)"/>
			
			<!-- Strict Budget Reservation Ceiling -->
			<line x1="20" y1="120" x2="380" y2="120" stroke="#111114" stroke-width="1.8" stroke-dasharray="4 3"/>
			<text x="25" y="112" font-family="'JetBrains Mono', monospace" font-size="9" fill="#111114" font-weight="600">RESERVATION CEILING ($0.0500)</text>
			
			${bars}
			
			<!-- Final Settled Floor -->
			<line x1="25" y1="150" x2="235" y2="150" stroke="#18a957" stroke-width="1.6"/>
			<text x="245" y="153" font-family="'JetBrains Mono', monospace" font-size="9" fill="#18a957" font-weight="600">SETTLED: $0.0482</text>
			
			<!-- Annotation for 429 -->
			<text x="240" y="175" font-family="'JetBrains Mono', monospace" font-size="9" fill="#ff4d4d">429 BUDGET_EXCEEDED</text>
			<text x="25" y="222" font-family="'JetBrains Mono', monospace" font-size="9" fill="#6b6a66">50 CONCURRENT ASYNC REQUESTS — ZERO OVER-ALLOCATION</text>
		`;
	}
	drawViz1();
	drawViz2();

	/* ---------- Hero canvas: drifting mesh grid ---------- */
	const canvas = $("#hero-canvas");
	if (canvas && !reduceMotion) {
		const ctx = canvas.getContext("2d");
		let W,
			H,
			dpr,
			pts = [],
			_raf;
		function resize() {
			dpr = Math.min(window.devicePixelRatio || 1, 2);
			W = canvas.clientWidth;
			H = canvas.clientHeight;
			canvas.width = W * dpr;
			canvas.height = H * dpr;
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
			const count = Math.min(65, Math.floor((W * H) / 24000));
			pts = [];
			for (let i = 0; i < count; i++) {
				pts.push({
					x: Math.random() * W,
					y: Math.random() * H,
					vx: (Math.random() - 0.5) * 0.22,
					vy: (Math.random() - 0.5) * 0.22,
					c: Math.random() > 0.78,
				});
			}
		}
		function frame() {
			ctx.clearRect(0, 0, W, H);
			// faint grid
			ctx.strokeStyle = "rgba(255,255,255,0.035)";
			ctx.lineWidth = 1;
			const g = 64;
			ctx.beginPath();
			for (let x = 0; x < W; x += g) {
				ctx.moveTo(x, 0);
				ctx.lineTo(x, H);
			}
			for (let y = 0; y < H; y += g) {
				ctx.moveTo(0, y);
				ctx.lineTo(W, y);
			}
			ctx.stroke();
			// connections
			for (let i = 0; i < pts.length; i++) {
				const a = pts[i];
				a.x += a.vx;
				a.y += a.vy;
				if (a.x < 0 || a.x > W) a.vx *= -1;
				if (a.y < 0 || a.y > H) a.vy *= -1;
				for (let j = i + 1; j < pts.length; j++) {
					const b = pts[j];
					const dx = a.x - b.x,
						dy = a.y - b.y,
						d = Math.hypot(dx, dy);
					if (d < 115) {
						ctx.strokeStyle = `rgba(243,241,234,${(1 - d / 115) * 0.09})`;
						ctx.beginPath();
						ctx.moveTo(a.x, a.y);
						ctx.lineTo(b.x, b.y);
						ctx.stroke();
					}
				}
			}
			// node points
			for (const p of pts) {
				ctx.fillStyle = p.c ? "rgba(31,68,255,0.85)" : "rgba(243,241,234,0.45)";
				ctx.beginPath();
				ctx.arc(p.x, p.y, p.c ? 1.8 : 1.2, 0, Math.PI * 2);
				ctx.fill();
			}
			_raf = requestAnimationFrame(frame);
		}
		resize();
		frame();
		let rt;
		window.addEventListener("resize", () => {
			clearTimeout(rt);
			rt = setTimeout(resize, 200);
		});
	}

	/* ---------- Quickstart code switcher & copy ---------- */
	const codeSnippets = {
		"curl-sh": `# On Linux / macOS / Git Bash:
curl http://localhost:8000/v1/chat/completions \\
  -H "Authorization: Bearer mr_live_demo_key" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "modelrail-fast",
    "messages": [{"role": "user", "content": "echo: hello ModelRail"}]
  }'`,
		"curl-ps": `# On Windows PowerShell (escape inner quotes for curl.exe):
curl.exe http://localhost:8000/v1/chat/completions \`
  -H "Authorization: Bearer mr_live_demo_key" \`
  -H "Content-Type: application/json" \`
  -d '{\\"model\\": \\"modelrail-fast\\", \\"messages\\": [{\\"role\\": \\"user\\", \\"content\\": \\"echo: hello ModelRail\\"}]}'`,
		"ps-irm": `# Using native PowerShell Invoke-RestMethod:
Invoke-RestMethod -Uri http://localhost:8000/v1/chat/completions \`
  -Method Post \`
  -Headers @{ Authorization = "Bearer mr_live_demo_key" } \`
  -ContentType "application/json" \`
  -Body '{"model": "modelrail-fast", "messages": [{"role": "user", "content": "echo: hello ModelRail"}]}'`,
		python: `from openai import OpenAI

# Drop-in OpenAI client configuration
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="mr_live_demo_key",
)

response = client.chat.completions.create(
    model="modelrail-fast",
    messages=[{"role": "user", "content": "echo: hello ModelRail"}],
)
print(response.choices[0].message.content)`,
	};

	const codeContent = $("#qs-code-content");
	let currentTab = "curl-sh";
	function setCode(tabKey) {
		currentTab = tabKey;
		if (codeContent) codeContent.textContent = codeSnippets[tabKey] || "";
	}
	setCode("curl-sh");

	const tabs = $$(".qs-tab");
	tabs.forEach((tab) => {
		tab.addEventListener("click", () => {
			tabs.forEach((t) => {
				t.classList.remove("active");
				t.setAttribute("aria-selected", "false");
			});
			tab.classList.add("active");
			tab.setAttribute("aria-selected", "true");
			setCode(tab.dataset.tab);
		});
	});

	const copyBtn = $("#qs-copy-btn");
	if (copyBtn) {
		copyBtn.addEventListener("click", async () => {
			const text = codeSnippets[currentTab] || "";
			try {
				await navigator.clipboard.writeText(text);
				copyBtn.classList.add("copied");
				copyBtn.querySelector("span").textContent = "Copied!";
				setTimeout(() => {
					copyBtn.classList.remove("copied");
					copyBtn.querySelector("span").textContent = "Copy";
				}, 2000);
			} catch (_err) {
				// Fallback
				const ta = document.createElement("textarea");
				ta.value = text;
				document.body.appendChild(ta);
				ta.select();
				document.execCommand("copy");
				document.body.removeChild(ta);
				copyBtn.classList.add("copied");
				copyBtn.querySelector("span").textContent = "Copied!";
				setTimeout(() => {
					copyBtn.classList.remove("copied");
					copyBtn.querySelector("span").textContent = "Copy";
				}, 2000);
			}
		});
	}

	/* ---------- Gateway lifecycle simulator & demo test cases ---------- */
	const simBtn = $("#qs-sim-btn");
	const steps = $$(".qs-step");
	const simJson = $("#qs-sim-json");
	const simBadge = $("#qs-sim-badge");
	const caseBtns = $$(".sim-case-btn");

	const simTestCases = {
		"happy-path": {
			badge: "PAYLOAD RESPONSE (STATUS 200 OK)",
			steps: [
				{ title: "1. Auth & Tenant Resolution", desc: "Key verified · Project: demo-app (fd2a719f)" },
				{ title: "2. Two-Phase Budget Reservation", desc: "Reserved $0.000030 (Max 2,048 tokens worst-case)" },
				{ title: "3. Policy Routing & Circuit Check", desc: "Alias: modelrail-fast → Selected: mock-1 (Circuit: CLOSED)" },
				{ title: "4. Provider Execution & Latency", desc: "Latency: 22ms · HTTP 200 OK normalized" },
				{ title: "5. Settlement & Audit Persistence", desc: "Charged $0.000018 (28 tokens) · Surplus $0.000012 released" },
			],
			response: {
				id: "chatcmpl-mr_7a4b89ef",
				object: "chat.completion",
				created: 1729938120,
				model: "modelrail-fast",
				choices: [
					{
						index: 0,
						message: {
							role: "assistant",
							content: "ModelRail gateway operational. Provider: mock-1. Latency: 22ms. Duplicate tokens: 0.",
						},
						finish_reason: "stop",
					},
				],
				usage: {
					prompt_tokens: 12,
					completion_tokens: 16,
					total_tokens: 28,
				},
				modelrail: {
					request_id: "req_01jbfa84k9",
					attempt_id: "att_01jbfa84k9_01",
					provider: "mock-1",
					cost_usd: 0.000018,
					settlement: "settled",
				},
			},
		},
		"failover": {
			badge: "PAYLOAD RESPONSE (STATUS 200 OK — VIA FALLBACK)",
			steps: [
				{ title: "1. Auth & Failure Flag Injected", desc: "Key verified · Injected payload: [fail:primary=outage]" },
				{ title: "2. Two-Phase Budget Reservation", desc: "Reserved $0.000030 on project demo-app" },
				{ title: "3. Primary Mock Outage Detected", desc: "mock-1 returned HTTP 503 · attempt_01 logged as failed" },
				{ title: "4. Standby Route Promoted", desc: "Rerouted to mock-secondary in 2ms · attempt_02 succeeded" },
				{ title: "5. Single-Attempt Settlement", desc: "Charged $0.000022 on attempt_02 · Exactly 0 duplicate billing" },
			],
			response: {
				id: "chatcmpl-mr_98ef1a3c",
				object: "chat.completion",
				created: 1729938150,
				model: "modelrail-resilient",
				choices: [
					{
						index: 0,
						message: {
							role: "assistant",
							content: "Fallback response: still works under simulated primary failure.",
						},
						finish_reason: "stop",
					},
				],
				usage: {
					prompt_tokens: 14,
					completion_tokens: 18,
					total_tokens: 32,
				},
				modelrail: {
					request_id: "req_01jbfb19x0",
					attempt_id: "att_01jbfb19x0_02",
					provider: "mock-secondary",
					attempts: 2,
					fallback_reason: "connection:mock",
					cost_usd: 0.000022,
					settlement: "settled",
				},
			},
		},
		"circuit-breaker": {
			badge: "CIRCUIT STATE EVENT (CIRCUIT BREAKER: OPEN)",
			steps: [
				{ title: "1. Failure Counter Threshold", desc: "Primary upstream consecutive 503 failures = 3 (Threshold: 3)" },
				{ title: "2. Finite-State Transition", desc: "Breaker tripped from CLOSED → OPEN (Degradation confirmed)" },
				{ title: "3. Fast-Fail Short Circuit", desc: "Subsequent requests bypass failing upstream with 0ms hang" },
				{ title: "4. Traffic Evacuation", desc: "100% of consumer traffic promoted to standby fallback" },
				{ title: "5. Telemetry & Transition Event", desc: "Emitted modelrail_circuit_transitions_total{state='open'} +1" },
			],
			response: {
				event: "circuit_breaker_transition",
				provider: "mock-1",
				route: "modelrail-fast",
				state: "OPEN",
				threshold_failures: 3,
				cool_down_seconds: 30,
				subsequent_requests: "routed_to_fallback",
				telemetry: {
					metric: "modelrail_circuit_transitions_total",
					labels: { provider: "mock-1", to_state: "open" },
					status: "active_protection",
				},
			},
		},
		"budget-429": {
			badge: "ERROR ENVELOPE (STATUS 429 TOO MANY REQUESTS)",
			steps: [
				{ title: "1. Project Quota Lookup", desc: "Project 'demo-app' balance remaining: $0.000020" },
				{ title: "2. Concurrency Burst Intercept", desc: "50 parallel async requests competing for budget lock" },
				{ title: "3. Two-Phase Reservation Attempt", desc: "Request requires worst-case ceiling: $0.000030" },
				{ title: "4. Quota Enforcement", desc: "Balance insufficient ($0.000020 < $0.000030) · Reservation refused" },
				{ title: "5. Safe Rejection & Zero Leak", desc: "Rejected with 429 budget_exceeded · Balance remains intact" },
			],
			response: {
				error: {
					message: "project budget limit exceeded ($0.000020 remaining, $0.000030 required for worst-case reservation)",
					type: "insufficient_quota",
					code: "budget_exceeded",
				},
				modelrail: {
					tenant_project_id: "fd2a719f-aaa6-4882-a1cb-5ba12fe33b77",
					budget_remaining_usd: 0.000020,
					reservation_requested_usd: 0.000030,
					over_allocation_prevented: true,
				},
			},
		},
		"idempotency": {
			badge: "PAYLOAD RESPONSE (STATUS 200 OK — REPLAYED)",
			steps: [
				{ title: "1. Idempotency Header Received", desc: "Header detected: Idempotency-Key: idemp_9f82ab71c0" },
				{ title: "2. Atomic Ledger Query", desc: "Identified previous successful execution for key" },
				{ title: "3. Provider Execution Bypassed", desc: "Zero upstream provider calls dispatched" },
				{ title: "4. Spend Deduplication", desc: "Usage tokens = 0 · Budget deduction = $0.000000" },
				{ title: "5. Cached Payload Replay", desc: "Returned stored completion with x-modelrail-cached: true" },
			],
			response: {
				id: "chatcmpl-mr_7a4b89ef",
				object: "chat.completion",
				created: 1729938120,
				model: "modelrail-fast",
				choices: [
					{
						index: 0,
						message: {
							role: "assistant",
							content: "ModelRail gateway operational. Provider: mock-1. Latency: 22ms. Duplicate tokens: 0.",
						},
						finish_reason: "stop",
					},
				],
				usage: {
					prompt_tokens: 12,
					completion_tokens: 16,
					total_tokens: 28,
				},
				modelrail: {
					request_id: "req_01jbfa84k9",
					idempotent_replay: true,
					duplicate_charge_prevented: true,
					cost_usd: 0.0,
				},
			},
		},
		"eval-gate": {
			badge: "CI GATE EVALUATION REPORT (RELEASE BLOCKED)",
			steps: [
				{ title: "1. Held-Out Evaluation Dataset", desc: "Evaluated 30 held-out items across 4 capability categories" },
				{ title: "2. Baseline Model Scoring", desc: "mock-good achieved 92.4% aggregate accuracy" },
				{ title: "3. Candidate Model Scoring", desc: "mock-degraded scored 74.0% aggregate accuracy (-18.4% drop)" },
				{ title: "4. Threshold Check (< 5% Drop)", desc: "Performance regression delta 18.4% exceeds allowed 5.0%" },
				{ title: "5. GitHub Actions CI Block", desc: "Gate runner returned exit code 1 · Pull request release blocked" },
			],
			response: {
				gate_verdict: "FAILED",
				threshold_max_drop: 0.05,
				actual_drop: 0.184,
				action: "RELEASE_BLOCKED",
				category_breakdown: {
					reasoning: { baseline: 0.94, candidate: 0.72, delta: -0.22, status: "BREACHED" },
					extraction: { baseline: 0.90, candidate: 0.75, delta: -0.15, status: "BREACHED" },
					instruction_following: { baseline: 0.93, candidate: 0.78, delta: -0.15, status: "BREACHED" },
					refusal: { baseline: 0.92, candidate: 0.71, delta: -0.21, status: "BREACHED" },
				},
			},
		},
	};

	let activeCaseKey = "happy-path";
	function renderCaseLabels(caseKey) {
		const c = simTestCases[caseKey];
		if (!c) return;
		for (let i = 0; i < 5; i++) {
			const sTitle = $(`#s-title-${i + 1}`);
			const sDesc = $(`#s-desc-${i + 1}`);
			if (sTitle && c.steps[i]) sTitle.textContent = c.steps[i].title;
			if (sDesc && c.steps[i]) sDesc.textContent = c.steps[i].desc;
		}
		if (simBadge) simBadge.textContent = c.badge;
	}

	caseBtns.forEach((btn) => {
		btn.addEventListener("click", () => {
			if (simRunning) return;
			caseBtns.forEach((b) => b.classList.remove("active"));
			btn.classList.add("active");
			activeCaseKey = btn.dataset.case || "happy-path";
			renderCaseLabels(activeCaseKey);
			// Reset steps visual state
			steps.forEach((s) => s.classList.remove("active", "completed"));
			if (simJson) simJson.textContent = "";
		});
	});

	let simRunning = false;
	if (simBtn) {
		simBtn.addEventListener("click", () => {
			if (simRunning) return;
			simRunning = true;
			simBtn.disabled = true;
			simBtn.innerHTML = "<span>⏳</span> Executing Simulation...";

			const activeCase = simTestCases[activeCaseKey] || simTestCases["happy-path"];
			renderCaseLabels(activeCaseKey);

			steps.forEach((s) => {
				s.classList.remove("active", "completed");
			});
			if (simJson) simJson.textContent = "";

			let cur = 0;
			function advance() {
				if (cur < steps.length) {
					if (cur > 0) {
						steps[cur - 1].classList.remove("active");
						steps[cur - 1].classList.add("completed");
					}
					steps[cur].classList.add("active");
					cur++;
					setTimeout(advance, 260);
				} else {
					steps[steps.length - 1].classList.remove("active");
					steps[steps.length - 1].classList.add("completed");
					if (simJson) {
						simJson.textContent = JSON.stringify(activeCase.response, null, 2);
					}
					simBtn.disabled = false;
					simBtn.innerHTML = "<span>▶</span> Try Demo Simulation";
					simRunning = false;
				}
			}
			advance();
		});
	}

	/* ---------- Hero Try Demo Button -> Scroll to Simulator ---------- */
	function triggerSimulatorFromHero(e) {
		e.preventDefault();
		const qs = $("#quickstart");
		if (qs) {
			qs.scrollIntoView({ behavior: "smooth", block: "start" });
			const simPanel = $(".qs-sim-panel");
			if (simPanel) {
				simPanel.style.transition = "box-shadow 0.4s ease, border-color 0.4s ease";
				simPanel.style.boxShadow = "0 0 0 3px rgba(31, 68, 255, 0.45)";
				setTimeout(() => {
					simPanel.style.boxShadow = "";
				}, 2200);
			}
			setTimeout(() => {
				const runBtn = $("#qs-sim-btn");
				if (runBtn && !runBtn.disabled) {
					runBtn.click();
				}
			}, 750);
		}
	}
	const heroDemoBtn = $("#hero-try-demo-btn");
	if (heroDemoBtn) heroDemoBtn.addEventListener("click", triggerSimulatorFromHero);
	const tcDemoBtn = $("#tc-try-demo-btn");
	if (tcDemoBtn) tcDemoBtn.addEventListener("click", triggerSimulatorFromHero);

	/* ---------- Newsletter form ---------- */
	const form = $("#news-form"),
		msg = $("#news-msg");
	if (form) {
		form.addEventListener("submit", (e) => {
			e.preventDefault();
			const name = $("#nf-name").value.trim();
			const email = $("#nf-email").value.trim();
			const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
			if (!name) {
				msg.textContent = "Please enter your name.";
				msg.className = "news-msg err";
				return;
			}
			if (!valid) {
				msg.textContent = "Please enter a valid engineering email.";
				msg.className = "news-msg err";
				return;
			}
			msg.textContent = "Subscribed — the ModelRail architectural dispatch is on its way.";
			msg.className = "news-msg ok";
			form.reset();
		});
	}
})();