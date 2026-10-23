    // --- source text (canonical copy: shared/source-text/source_text.js) ---
    // The JavaScript side of shared/source-text/source_text.py, embedded as is
    // in the browser helpers (tests/source-text/test_source_text.js checks the
    // copies and that both give the same results). Emphasis placeholders
    // around <i>/<em> and <b>/<strong> text become *italic* and **bold** in
    // stFinish(); stSuperscript() writes m², 10⁻¹ or ^text^; stMarkLists()
    // writes the numbers the browser draws for an <ol>; ST_SPACES are the
    // non-breaking spaces that become plain spaces; stFold() is the text as
    // search matches it.
    const ST_EM = String.fromCharCode(2); const ST_EM_END = String.fromCharCode(3);
    const ST_STRONG = String.fromCharCode(4); const ST_STRONG_END = String.fromCharCode(5);
    const ST_MARKERS = ST_EM + ST_EM_END + ST_STRONG + ST_STRONG_END;
    const ST_WS = ' \t\r\f\v';
    const ST_SPACES = new RegExp('[' + String.fromCharCode(0xa0, 0x202f) + ']', 'g');
    const ST_SUP = new Map(Array.from('0123456789+-−=()', (c, k) => [c, '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾'[k]]));
    const ST_EMPHASIS = { i: [ST_EM, ST_EM_END], em: [ST_EM, ST_EM_END], b: [ST_STRONG, ST_STRONG_END], strong: [ST_STRONG, ST_STRONG_END] };

    function stMarkEmphasis(html) {
      return html.replace(/<[^>]*>/g, (tag) => {
        const e = /^<(\/?)(i|em|b|strong)(?:\s[^>]*)?>$/i.exec(tag);
        return e ? ST_EMPHASIS[e[2].toLowerCase()][e[1] ? 1 : 0] : tag;
      });
    }

    function stFinish(text) {
      if (!Array.from(ST_MARKERS).some((c) => text.includes(c))) return text;
      const out = []; const opened = []; let ws = [];
      let italic = 0; let bold = 0;
      const closeTo = (target) => {
        let keep = 0;
        while (keep < opened.length && target.has(opened[keep])) keep += 1;
        for (let k = opened.length - 1; k >= keep; k -= 1) out.push(opened[k]);
        opened.length = keep;
      };
      for (const c of text) {
        if (c === ST_EM) { italic += 1; continue; }
        if (c === ST_EM_END) { italic = Math.max(0, italic - 1); continue; }
        if (c === ST_STRONG) { bold += 1; continue; }
        if (c === ST_STRONG_END) { bold = Math.max(0, bold - 1); continue; }
        if (c === '\n') { closeTo(new Set()); out.push(...ws); ws = []; out.push(c); continue; }
        if (ST_WS.includes(c)) { ws.push(c); continue; }
        const target = new Set();
        if (bold > 0) target.add('**');
        if (italic > 0) target.add('*');
        closeTo(target);
        out.push(...ws); ws = [];
        for (const mark of ['**', '*']) {
          if (target.has(mark) && !opened.includes(mark)) { out.push(mark); opened.push(mark); }
        }
        out.push(c);
      }
      closeTo(new Set());
      out.push(...ws);
      return out.join('');
    }

    function stPlain(text) {
      return Array.from(text).filter((c) => !ST_MARKERS.includes(c)).join('');
    }

    function stSuperscript(text) {
      const core = text.replace(/^[ \t\r\f\v\n]+|[ \t\r\f\v\n]+$/g, '');
      if (!core) return text;
      const at = text.indexOf(core);
      const lead = text.slice(0, at); const trail = text.slice(at + core.length);
      if (Array.from(core).every((c) => ST_SUP.has(c))) return lead + Array.from(core, (c) => ST_SUP.get(c)).join('') + trail;
      return `${lead}^${core}^${trail}`;
    }

    const ST_ROMAN = [[1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'],
      [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']];
    const ST_STYLE_KIND = { 'lower-alpha': 'a', 'lower-latin': 'a', 'upper-alpha': 'A', 'upper-latin': 'A', 'lower-roman': 'i', 'upper-roman': 'I', decimal: '1' };

    function stListLabel(n, kind) {
      if (kind === 'I' || kind === 'i') {
        let out = '';
        for (const [value, numeral] of ST_ROMAN) {
          while (n >= value) { out += numeral; n -= value; }
        }
        return kind === 'I' ? out : out.toLowerCase();
      }
      if (kind === 'A' || kind === 'a') {
        let out = '';
        while (n > 0) {
          const r = (n - 1) % 26;
          n = Math.floor((n - 1) / 26);
          out = String.fromCharCode(kind.charCodeAt(0) + r) + out;
        }
        return out;
      }
      return String(n);
    }

    function stOlKind(attrs) {
      let m = /list-style-type\s*:\s*([a-z-]+)/i.exec(attrs);
      if (m && ST_STYLE_KIND[m[1].toLowerCase()]) return ST_STYLE_KIND[m[1].toLowerCase()];
      m = /\btype\s*=\s*"?([aAiI1])\b/.exec(attrs);
      return m ? m[1] : '1';
    }

    function stMarkLists(html, bullet = '- ') {
      const stack = [];
      return html.replace(/<(\/?)(ol|ul|li)\b([^>]*)>/gi, (tag, closing, name, attrs) => {
        name = name.toLowerCase();
        if (name === 'ol' || name === 'ul') {
          if (closing) stack.pop();
          else if (name === 'ul') stack.push(null);
          else {
            const start = /\bstart\s*=\s*"?(-?\d+)/.exec(attrs);
            stack.push([stOlKind(attrs), start ? Number(start[1]) : 1]);
          }
          return tag;
        }
        if (closing) return tag;
        const top = stack.length ? stack[stack.length - 1] : null;
        if (!top) return tag + '\n' + bullet;
        const value = /\bvalue\s*=\s*"?(-?\d+)/.exec(attrs);
        if (value) top[1] = Number(value[1]);
        const label = stListLabel(top[1], top[0]);
        top[1] += 1;
        return `${tag}\n${label}. `;
      });
    }

    function stFold(text) {
      return text.replace(/\*/g, '').split(String.fromCharCode(0xad)).join('');
    }
    // --- end source text ---
