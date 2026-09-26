"""Prompt-side contract text. One copy for every service.

`LATEX_SYSTEM_RULES` is prepended to every Class A generation prompt,
`NARRATIVE_PROSE_RULES` to every Class B (spoken script) prompt, and
`narrative_field_exemption` carves prose fields out of a JSON object that
mixes both. All injectors are idempotent: a prompt that already carries a
block is returned unchanged, so a per-call chokepoint and an explicit call
at the generator can both run (agents #516).
"""

from __future__ import annotations

LATEX_SYSTEM_RULES = r"""
=== MATHEMATICAL NOTATION / LATEX RULES (MANDATORY) ===

The frontend renders math with flutter_math_fork and will display EXACTLY
what you output. It cannot fix broken LaTeX. Follow these rules without
exception:

1. DELIMITERS
   - Wrap every math expression in $...$ (inline) or $$...$$ (display).
   - Do NOT use \( \) or \[ \] — only $ delimiters.
   - Correct:  The formula is $x^{2} + y^{2} = r^{2}$.
   - Wrong:    The formula is x^{2} + y^{2} = r^{2}. (bare, will not render)

2. BACKSLASH COMMANDS
   - Use a single backslash: \frac, \sqrt, \pi, \vec, \theta.
   - In JSON string values this appears as one literal backslash (JSON
     source shows \\; the parser resolves it to \).
   - Never output quadruple-backslash sequences such as \\\\frac.

3. SUB/SUPERSCRIPT BRACES
   - Multi-character super/subscripts MUST use braces.
   - Correct:  $x^{10}$, $a_{12}$, $10^{-34}$
   - Wrong:    $x^10$ (renders as x^1 followed by 0)
   - Single character without braces is acceptable: $x^2$, $a_1$.

4. CURRENCY DOLLAR SIGNS
   - Escape non-math $ as \$.
   - Correct:  The price is \$5.
   - Wrong:    The price is $5. (breaks math delimiter matching)

5. CHEMISTRY (USE \text{} FOR ELEMENT SYMBOLS)
   - Chemical formulas MUST use \text{} for element names and
     subscripts/superscripts for numbers and charges.
   - Water:          $\text{H}_{2}\text{O}$
   - Sulfuric acid:  $\text{H}_{2}\text{SO}_{4}$
   - Sulfate ion:    $\text{SO}_{4}^{2-}$
   - Iron(III) ion:  $\text{Fe}^{3+}$
   - Reaction:       $\text{2H}_{2} + \text{O}_{2} \rightarrow \text{2H}_{2}\text{O}$
   - Wrong:          H2O, H₂O, CO2 (bare text — will not render as chemistry)

   NOTE: \text{} is for chemistry and for labels INSIDE math.  Do NOT wrap
   plain English words in \text{} (e.g. $\text{Coulomb}$ is wrong — just
   write "Coulomb").

6. SCIENTIFIC NOTATION
   - Always $\times$ inside math, never × or x.
   - Correct:  $3 \times 10^{8}$
   - Wrong:    3 × 10^8, 3 x 10^8 (bare characters will not render)

7. ENCODING (UTF-8 ONLY)
   - Never emit mojibake sequences: Ï€, Ã, Â, Î±, Ï†, â€.
   - Use proper LaTeX instead: $\pi$, $\alpha$, $\phi$.

8. SUPPORTED COMMANDS (flutter_math_fork subset — do NOT use others)
   Greek lowercase: \alpha \beta \gamma \delta \epsilon \zeta \eta \theta
                    \iota \kappa \lambda \mu \nu \xi \pi \rho \sigma \tau
                    \phi \chi \psi \omega
   Greek uppercase: \Gamma \Delta \Theta \Lambda \Xi \Pi \Sigma \Phi \Psi \Omega
   Fractions:       \frac{a}{b}, \dfrac{a}{b}, \sqrt{x}, \sqrt[n]{x}
   Operators:       \times \div \pm \mp \cdot \leq \geq \neq \approx
                    \equiv \sim \cong \propto \infty \partial \nabla
   Arrows:          \rightarrow \Rightarrow \leftarrow \Leftarrow
                    \leftrightarrow \Leftrightarrow \mapsto \to
                    \rightleftharpoons
   Sets/Logic:      \in \notin \subset \supset \subseteq \cup \cap
                    \emptyset \forall \exists \mathbb{R} \mathbb{N}
                    \mathbb{Z} \mathbb{Q} \mathbb{C}
   Functions:       \sin \cos \tan \cot \sec \csc \log \ln \exp
                    \lim \max \min \sum \int \prod \iint \iiint \oint
   Decorations:     \vec{A} \hat{i} \bar{x} \dot{x} \overline{AB}
                    \underline{x} \tilde{x} \text{label} \mathbf{x}
                    \mathcal{L}
   Delimiters:      \left( \right), \left[ \right], \left\{ \right\},
                    \left| \right|, \langle \rangle
   Matrices:        \begin{pmatrix}...\end{pmatrix}, bmatrix, vmatrix
   - DO NOT use: \mathscr, \mathfrak, \cal
   - For literal { } inside math use \left\{ \right\} (with the backslash).

9. SPACING INSIDE MATH
   - $a \quad b$ (large), $a \qquad b$ (very large), $a \ b$ (normal).

10. NEVER OUTPUT THESE BARE CHARACTERS — ALWAYS USE THE LATEX COMMAND
    Math operators: × ÷ ± ∓ · √ ∞ ∂ ∇ ≤ ≥ ≠ ≈ ≡ ∼ ≅ ∝ ⊥ ∥
    Arrows:         → ← ↔ ⇒ ⇐ ⇔ ↑ ↓ ⇌ ↦
    Greek letters:  α β γ δ ε ζ η θ ι κ λ μ ν ξ π ρ σ τ υ φ χ ψ ω
                    Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω
    Set theory:     ∈ ∉ ⊂ ⊃ ⊆ ⊇ ∪ ∩ ∅ ∀ ∃ ∧ ∨ ¬ ℝ ℕ ℤ ℚ ℂ
    Calculus:       ∫ ∬ ∭ ∮ ∑ ∏ ℏ
    Sub/super:      ₀ ₁ ₂ ₃ ₄ ₅ ₆ ₇ ₈ ₉ ⁰ ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹ ⁺ ⁻
    Chemistry:      Write $\text{H}_{2}\text{O}$ NOT H₂O or H2O.
                    Write $\text{CO}_{2}$ NOT CO₂ or CO2.
                    Write $\text{NaHCO}_{3}$ NOT NaHCO₃.
    Fractions:      Write $\frac{1}{2}$ NOT ½. $\frac{1}{3}$ NOT ⅓.

=== PRE-SUBMIT CHECKLIST ===
[ ] All math wrapped in $...$ or $$...$$
[ ] No bare LaTeX commands outside delimiters
[ ] No mojibake characters anywhere in output
[ ] No bare Unicode math/Greek characters anywhere (see rule 10)
[ ] Multi-char sub/superscripts use { }
[ ] Currency $ escaped as \$
[ ] Chemistry uses \text{} for elements (never Unicode subscripts)
[ ] Scientific notation uses \times (not × or x)
[ ] Only commands from the supported list above
=== END LATEX RULES ===
"""

NARRATIVE_PROSE_RULES = r"""
=== NARRATIVE PROSE RULES (MANDATORY) ===

This output is a SCRIPT: dialogue and narration that a student reads and that a
text-to-speech voice reads aloud. It is not a worksheet and not a set of notes.

1. NO LATEX, NO MATH MARKUP, ANYWHERE
   - Never use $...$ or $$...$$.
   - Never use a backslash command: no \ldots, \dots, \text, \frac, \times,
     \alpha, \rightleftharpoons, \textmu — none of them.
   - These do not render in a narrated script; the student sees the raw
     characters and the voice reads them out loud.

2. PUNCTUATION IS PLAIN TEXT
   - A trailing-off pause is "..." or "…" — NOT $\ldots$.
   - A dash is "-" or "—". A degree is "degrees".

3. SAY QUANTITIES THE WAY A PERSON SAYS THEM
   - "three times ten to the eighth metres per second", not $3 \times 10^{8}$.
   - "one half", not \frac{1}{2}. "about five percent", not 5\%.
   - "twenty-five degrees Celsius", not $25^\circ C$.

4. SAY CHEMISTRY AND UNITS THE WAY A PERSON SAYS THEM
   - "carbon dioxide" or "C-O-two", not $\text{CO}_{2}$ and not CO₂.
   - "haemoglobin", "micrometre", "millilitre" — spelled out, not \textmu m.
   - A reversible reaction is "turns back and forth into", not
     $\rightleftharpoons$.

5. GREEK LETTERS AND SYMBOLS ARE SPOKEN NAMES
   - "alpha", "beta", "pi" — not α, β, π and not $\alpha$, $\beta$, $\pi$.

6. ENCODING (UTF-8 ONLY)
   - Never emit mojibake sequences: Ï€, Ã, Â, Î±, Ï†, â€.

=== PRE-SUBMIT CHECKLIST ===
[ ] Not a single $ character anywhere in the script
[ ] Not a single backslash command anywhere in the script
[ ] Every number, unit, formula and symbol written the way it is SPOKEN
[ ] Reads correctly out loud with no symbol names left in it
=== END NARRATIVE PROSE RULES ===
"""

# The first line of each block doubles as its presence marker, so the
# idempotency check cannot drift from the text it guards.
LATEX_RULES_MARKER = LATEX_SYSTEM_RULES.strip().splitlines()[0]
NARRATIVE_RULES_MARKER = NARRATIVE_PROSE_RULES.strip().splitlines()[0]


def inject_latex_rules(prompt: str) -> str:
    """Prepend `LATEX_SYSTEM_RULES`. Idempotent."""
    if LATEX_RULES_MARKER in prompt:
        return prompt
    return f"{LATEX_SYSTEM_RULES}\n\n{prompt}"


def inject_narrative_prose_rules(prompt: str) -> str:
    """Prepend `NARRATIVE_PROSE_RULES`. Idempotent."""
    if NARRATIVE_RULES_MARKER in prompt:
        return prompt
    return f"{NARRATIVE_PROSE_RULES}\n\n{prompt}"


def has_formatting_contract(prompt: str) -> bool:
    """True when either rules block is already present."""
    return LATEX_RULES_MARKER in prompt or NARRATIVE_RULES_MARKER in prompt


def narrative_field_exemption(*fields: str) -> str:
    r"""Clause exempting named JSON fields from the math rules.

    Append AFTER `inject_latex_rules` when one JSON object carries both a
    narration script and the MCQs that test it::

        prompt = inject_latex_rules(prompt)
        prompt += narrative_field_exemption("story_script", "story_sections[].content")
    """
    listed = "\n".join(f"   - {f}" for f in fields)
    return f"""

=== EXEMPTION: NARRATIVE FIELDS ARE PLAIN PROSE (OVERRIDES THE RULES ABOVE) ===

The LaTeX rules above apply ONLY to question, option and explanation fields.
They DO NOT apply to these fields:
{listed}

Those fields are spoken dialogue and narration. A text-to-speech voice reads
them aloud and the student sees them as plain text, so inside them:

   - Use NO $ delimiters and NO backslash commands. Not \\ldots, not \\text,
     not \\times, not \\frac, not \\textmu, not \\rightleftharpoons.
   - A trailing-off pause is "..." — never $\\ldots$.
   - Write quantities, units, chemistry and Greek letters the way a person
     SAYS them: "carbon dioxide" not $\\text{{CO}}_{{2}}$; "three times ten to
     the eighth" not $3 \\times 10^{{8}}$; "alpha" not $\\alpha$.
   - Bare Unicode (H₂O, α, ×) is also wrong here — spell it out in words.

Check before emitting: the narrative fields above must contain no $ character
and no backslash command, and must read correctly out loud.
=== END EXEMPTION ===
"""
