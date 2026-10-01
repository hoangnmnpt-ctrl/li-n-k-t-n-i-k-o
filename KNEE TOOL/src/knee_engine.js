/* =====================================================================
 * KNEE ENGINE — Liên kết knee kèo bản đầu bu lông
 * AISC 360-10 (LRFD) + AISC Design Guide 4 (2003), Design Guide 16 (2002),
 * Design Guide 39 (2023, phụ lục A — Yc phía gối).
 * Đơn vị nội bộ: N, mm, MPa (N/mm²). Hiển thị: kN, kN·m.
 * ===================================================================== */
(function (root) {
  'use strict';

  const E = 200000;          // MPa
  const IN = 25.4;           // mm / in
  const D2R = Math.PI / 180;
  const cosd = (a) => Math.cos(a * D2R);
  const sind = (a) => Math.sin(a * D2R);

  /* ---------------- Thư viện vật liệu ---------------- */
  const MATERIALS = {
    'Q345':      { Fy: 345, Fu: 470 },
    'Q235':      { Fy: 235, Fu: 370 },
    'SS400':     { Fy: 245, Fu: 400 },
    'SM490':     { Fy: 325, Fu: 490 },
    'CCT34':     { Fy: 220, Fu: 340 },
    'CCT38':     { Fy: 240, Fu: 380 },
    'CCT42':     { Fy: 260, Fu: 420 },
    'A36':       { Fy: 250, Fu: 400 },
    'A572 Gr50': { Fy: 345, Fu: 450 },
    'A992':      { Fy: 345, Fu: 450 },
  };

  // Bu lông: 8.8 ≈ A325M, 10.9 ≈ A490M (AISC 360-10 Table J3.2, giá trị ksi quy đổi)
  const BOLT_GRADES = {
    '8.8':  { Fnt: 620.5, FnvN: 372.3, FnvX: 468.8, pre: 'A325', label: 'Cấp 8.8 (≈ A325M)' },
    '10.9': { Fnt: 779.1, FnvN: 468.8, FnvX: 579.2, pre: 'A490', label: 'Cấp 10.9 (≈ A490M)' },
    'A325': { Fnt: 620.5, FnvN: 372.3, FnvX: 468.8, pre: 'A325', label: 'ASTM A325M' },
    'A490': { Fnt: 779.1, FnvN: 468.8, FnvX: 579.2, pre: 'A490', label: 'ASTM A490M' },
  };
  const BOLT_DIAS = [16, 20, 22, 24, 27, 30, 36];
  // Lực căng trước tối thiểu Tb (kN) — AISC 360-10 Table J3.1M
  const PRETENSION = {
    A325: { 16: 91, 20: 142, 22: 176, 24: 205, 27: 267, 30: 326, 36: 475 },
    A490: { 16: 114, 20: 179, 22: 221, 24: 257, 27: 334, 30: 408, 36: 595 },
  };
  // Lỗ tiêu chuẩn (mm) — Table J3.3M
  const HOLE_STD = { 16: 18, 20: 22, 22: 24, 24: 27, 27: 30, 30: 33, 36: 39 };
  // Khoảng cách mép tối thiểu (mm) — Table J3.4M [mép cắt, mép cán/cắt nhiệt]
  const EDGE_MIN = { 16: [28, 22], 20: [34, 26], 22: [38, 28], 24: [42, 30], 27: [48, 34], 30: [52, 38], 36: [64, 46] };
  const ELECTRODES = { 'E60XX': 413.7, 'E70XX': 482.6, 'E80XX': 551.6 };

  const holeDia = (db) => HOLE_STD[db] || db + 3;
  const edgeMin = (db, sheared) => {
    const r = EDGE_MIN[db];
    if (r) return sheared ? r[0] : r[1];
    return (sheared ? 1.75 : 1.25) * db;
  };
  // Kích thước hàn góc tối thiểu — Table J2.4 (theo phần mỏng hơn)
  const weldMin = (t) => (t <= 6 ? 3 : t <= 13 ? 5 : t <= 19 ? 6 : 8);

  function material(name, custom) {
    if (name === 'Tùy chọn' && custom) return { name: 'Tùy chọn', Fy: +custom.Fy, Fu: +custom.Fu };
    const m = MATERIALS[name] || MATERIALS['Q345'];
    return { name: MATERIALS[name] ? name : 'Q345', Fy: m.Fy, Fu: m.Fu };
  }

  /* ---------------- Tiết diện theo quy cách "I (h1-h2)-tw/bf-tf" ---------------- */
  function isNum(s) { return s !== '' && s != null && !isNaN(+s); }
  function parseSection(str) {
    const clean = String(str || '').trim().toUpperCase();
    if (!clean) return { ok: false };
    const po = clean.indexOf('('), pc = clean.indexOf(')');
    if (po >= 0 && pc > po && clean.indexOf('-') >= 0) {
      const hs = clean.slice(po + 1, pc).split('-').map((x) => x.trim());
      const nums = clean.slice(pc + 1).replace(/\//g, '-').split('-').map((x) => x.trim()).filter(isNum).map(Number);
      if (hs.length >= 2 && isNum(hs[0]) && isNum(hs[1]) && nums.length >= 3)
        return { ok: true, h1: +hs[0], h2: +hs[1], tw: nums[0], bf: nums[1], tf: nums[2], tapered: +hs[0] !== +hs[1] };
    }
    if (clean.indexOf('I') >= 0 || clean.indexOf('H') >= 0 || /^[\d.\s\-\/]+$/.test(clean)) {
      const nums = clean.replace(/[IH]/g, '').replace(/\//g, '-').split('-').map((x) => x.trim()).filter(isNum).map(Number);
      if (nums.length >= 4) return { ok: true, h1: nums[0], h2: nums[0], tw: nums[1], bf: nums[2], tf: nums[3], tapered: false };
    }
    return { ok: false };
  }

  function memberAtJoint(m, label) {
    const p = parseSection(m.sec);
    if (!p.ok) throw new Error('Không đọc được tiết diện ' + label + ': "' + m.sec + '". Quy cách: I (h1-h2)-tw/bf-tf hoặc I h-tw/bf-tf');
    const d = m.jointEnd === 'end' ? p.h2 : p.h1;
    const L = Math.max(+m.L || 0, 1);
    const beta = Math.atan(Math.abs(p.h1 - p.h2) / L) / D2R;
    const A = 2 * p.bf * p.tf + (d - 2 * p.tf) * p.tw;
    return { label, sec: m.sec, d, tw: p.tw, bf: p.bf, tf: p.tf, beta, L, A, mat: material(m.mat, m.matCustom), h1: p.h1, h2: p.h2, tapered: p.tapered };
  }

  function fold(a) { let y = Math.abs(a) % 180; if (y > 90) y = 180 - y; return y; }

  /* ---------------- Yield-line Y cho bản đầu (DG16) ---------------- */
  // h: đo từ mặt ngoài cánh nén (DG16). Trả về {Y, formula, config}
  function endPlateY(cfg, o) {
    const { bp, g, pfi, pfo, pb, h0, h, de } = o; // h = mảng h hàng trong (từ ngoài vào)
    const s = 0.5 * Math.sqrt(bp * g);
    const pf = Math.min(pfi, s);
    let Y, f;
    switch (cfg) {
      case '2FU':
        Y = bp / 2 * (h[0] * (1 / pf + 1 / s) - 0.5) + 2 / g * (h[0] * (pf + s));
        f = 'Y = bp/2·[h1(1/pf + 1/s) − 1/2] + 2/g·[h1(pf + s)]   (DG16 Table 3-2)';
        break;
      case '4FU':
        Y = bp / 2 * (h[0] / pf + h[1] / s - 0.5) + 2 / g * (h[0] * (pf + 0.75 * pb) + h[1] * (s + 0.25 * pb)) + g / 2;
        f = 'Y = bp/2·[h1/pf + h2/s − 1/2] + 2/g·[h1(pf + 0.75pb) + h2(s + 0.25pb)] + g/2   (DG16 Table 3-3)';
        break;
      case '4E':
        Y = bp / 2 * (h[0] * (1 / pf + 1 / s) + h0 / pfo - 0.5) + 2 / g * (h[0] * (pf + s));
        f = 'Y = bp/2·[h1(1/pf,i + 1/s) + h0(1/pf,o) − 1/2] + 2/g·[h1(pf,i + s)]   (DG16 Table 4-2)';
        break;
      case '4ES':
        if (s < de) {
          Y = bp / 2 * (h[0] * (1 / pf + 1 / s) + h0 * (1 / s + 1 / pfo)) + 2 / g * (h[0] * (pf + s) + h0 * (s + pfo));
          f = 'Case 1 (s < de): Y = bp/2·[h1(1/pf,i + 1/s) + h0(1/s + 1/pf,o)] + 2/g·[h1(pf,i + s) + h0(s + pf,o)]   (DG16 Table 4-3)';
        } else {
          Y = bp / 2 * (h[0] * (1 / pf + 1 / s) + h0 * (1 / pfo + 1 / (2 * de))) + 2 / g * (h[0] * (pf + s) + h0 * (de + pfo));
          f = 'Case 2 (s ≥ de): Y = bp/2·[h1(1/pf,i + 1/s) + h0(1/pf,o + 1/(2de))] + 2/g·[h1(pf,i + s) + h0(de + pf,o)]   (DG16 Table 4-3)';
        }
        break;
      case 'MRE 1/2':
        Y = bp / 2 * (h[0] / pf + h[1] / s + h0 / pfo - 0.5) + 2 / g * (h[0] * (pf + 0.75 * pb) + h[1] * (s + 0.25 * pb)) + g / 2;
        f = 'Y = bp/2·[h1/pf,i + h2/s + h0/pf,o − 1/2] + 2/g·[h1(pf,i + 0.75pb) + h2(s + 0.25pb)] + g/2   (DG16 Table 4-4)';
        break;
      case 'MRE 1/3':
        Y = bp / 2 * (h[0] / pf + h[2] / s + h0 / pfo - 0.5) + 2 / g * (h[0] * (pf + 1.5 * pb) + h[2] * (s + 0.5 * pb)) + g / 2;
        f = 'Y = bp/2·[h1/pf,i + h3/s + h0/pf,o − 1/2] + 2/g·[h1(pf,i + 1.5pb) + h3(s + 0.5pb)] + g/2   (DG16 Table 4-5)';
        break;
      default:
        throw new Error('Cấu hình bu lông không hỗ trợ: ' + cfg);
    }
    return { Y, s, pf, formula: f };
  }

  /* ---------------- Yield-line Yc phía gối (DG4 Table 3.4 / DG39 App. A) ---------------- */
  // rows: [{d, s}] hàng chịu kéo; d đo từ tâm cánh nén (DG4/DG39)
  function supportYc(cond, o) {
    const { b, g, rows, psiRaw, psoRaw, pcpRaw, de } = o;
    const s = 0.5 * Math.sqrt(b * g);
    const cap = (x) => Math.max(Math.min(x, s), 1);
    let Y, f, note = '';
    if (rows.length === 1) {
      const h1 = rows[0].d;
      switch (cond) {
        case 'cont_unstiff':
          Y = b * h1 / s + 4 * h1 * s / g;
          f = 'Yc = bcf·h1/s + 4h1·s/g   (DG39 Table A-1a)'; break;
        case 'cont_stiff': {
          const psi = cap(psiRaw);
          Y = b / 2 * h1 * (1 / psi + 1 / s) + 2 / g * h1 * (psi + s);
          f = 'Yc = bcf/2·h1(1/psi + 1/s) + 2/g·h1(psi + s)   (DG39 Table A-1b), psi = ' + psi.toFixed(1); break;
        }
        case 'top_unstiff':
          Y = b / 2 * (h1 / s - 0.5) + 2 / g * h1 * (s + de) + g / 4;
          f = 'Yc = bcf/2·[h1/s − 1/2] + 2/g·h1(s + de) + g/4   (DG39 Table A-1c), de = ' + de.toFixed(1); break;
        case 'top_cap': {
          const pcp = cap(pcpRaw);
          Y = b / 2 * h1 * (1 / pcp + 1 / s) + 2 / g * h1 * (pcp + s);
          f = 'Yc = bcf/2·h1(1/pcp + 1/s) + 2/g·h1(pcp + s)   (DG39 Table A-1d), pcp = ' + pcp.toFixed(1); break;
        }
        default: throw new Error('Điều kiện gối không hợp lệ: ' + cond);
      }
    } else {
      // 2 hàng: hàng "gần" (near) là hàng gần sườn/đỉnh; ho = hàng xa tâm nén nhất
      const sorted = rows.slice().sort((a, c) => c.d - a.d);
      const ho = sorted[0].d, hi = sorted[1].d;
      const c = Math.abs(sorted[0].s - sorted[1].s);
      if (rows.length > 2) note = 'Có > 2 hàng kéo: Yc chỉ tính với 2 hàng ngoài cùng (thiên về an toàn).';
      switch (cond) {
        case 'cont_unstiff':
          Y = b / 2 * (hi / s + ho / s) + 2 / g * (hi * (s + 0.75 * c) + ho * (s + 0.25 * c) + c * c / 2) + g / 2;
          f = 'Yc = bcf/2·[h1/s + h0/s] + 2/g·[h1(s + 3c/4) + h0(s + c/4) + c²/2] + g/2   (DG4 Table 3.4), c = ' + c.toFixed(1); break;
        case 'cont_stiff': {
          const psi = cap(psiRaw), pso = cap(psoRaw);
          if (o.stiffBetween) {
            Y = b / 2 * (hi * (1 / s + 1 / psi) + ho * (1 / s + 1 / pso)) + 2 / g * (hi * (s + psi) + ho * (s + pso));
            f = 'Yc = bcf/2·[h1(1/s + 1/psi) + h0(1/s + 1/pso)] + 2/g·[h1(s + psi) + h0(s + pso)]   (DG4 Table 3.4 có sườn), psi = ' + psi.toFixed(1) + ', pso = ' + pso.toFixed(1);
          } else {
            // sườn nằm phía ngoài 2 hàng (flush 4 bu lông) — DG39 Table A-2b [VERIFY thứ tự hệ số c]
            Y = b / 2 * (ho / psi + hi / s) + 2 / g * (ho * (psi + 0.25 * c) + hi * (s + 0.75 * c)) + g / 2;
            f = 'Yc = bcf/2·[hn/psi + hf/s] + 2/g·[hn(psi + c/4) + hf(s + 3c/4)] + g/2   (DG39 Table A-2b) [VERIFY]';
          }
          break;
        }
        case 'top_unstiff':
          Y = b / 2 * (hi / s - 0.5) + 2 / g * (ho * (de + 0.25 * c) + hi * (s + 0.75 * c)) + 3 * g / 4;
          f = 'Yc = bcf/2·[h1/s − 1/2] + 2/g·[h0(de + c/4) + h1(s + 3c/4)] + 3g/4   (DG39 Table A-2d) [VERIFY], de = ' + de.toFixed(1); break;
        case 'top_cap': {
          const pcp = cap(pcpRaw);
          Y = b / 2 * (ho / pcp + hi / s) + 2 / g * (ho * (pcp + 0.25 * c) + hi * (s + 0.75 * c)) + g / 2;
          f = 'Yc = bcf/2·[h0/pcp + h1/s] + 2/g·[h0(pcp + c/4) + h1(s + 3c/4)] + g/2   (DG39 Table A-2e) [VERIFY], pcp = ' + pcp.toFixed(1); break;
        }
        default: throw new Error('Điều kiện gối không hợp lệ: ' + cond);
      }
    }
    return { Y, s, formula: f, note };
  }

  /* ---------------- Lực bu lông có nhổ (Kennedy hiệu chỉnh, DG16) ---------------- */
  function kennedy(o) {
    const { t, Fy, b, db, Fnt, pfi, pfo, edgeOut } = o;
    const wc = b / 2 - (db + IN / 16);
    const a = Math.max(IN * (3.682 * Math.pow(t / db, 3) - 0.085), 0.1);
    const Fi = (t * t * Fy * (0.85 * b / 2 + 0.8 * wc) + Math.PI * Math.pow(db, 3) * Fnt / 8) / (4 * pfi);
    const radI = Fy * Fy - 3 * Math.pow(Fi / (wc * t), 2);
    const Qi = radI > 0 ? wc * t * t / (4 * a) * Math.sqrt(radI) : NaN;
    let ao = null, Fo = null, Qo = null;
    if (pfo) {
      ao = Math.min(a, edgeOut);
      Fo = Fi * pfi / pfo;
      const radO = Fy * Fy - 3 * Math.pow(Fo / (wc * t), 2);
      Qo = radO > 0 ? wc * t * t / (4 * ao) * Math.sqrt(radO) : NaN;
    }
    return { wc, a, Fi, Qi, ao, Fo, Qo };
  }

  function boltMoments(cfgExt, rowsD, Pt, Tb, Qi, Qo) {
    // rowsD: {d0 (ngoài) | null, inner: [d1, d2, d3]}
    const inner = rowsD.inner;
    const sumD = (rowsD.d0 || 0) + inner.reduce((x, y) => x + y, 0);
    const Mnp = 2 * Pt * sumD;
    let cases;
    if (cfgExt) {
      const d0 = rowsD.d0, d1 = inner[0] || 0, d2 = inner[1] || 0, d3 = inner[2] || 0;
      const po = Pt - Qo, pi = Pt - Qi;
      cases = [
        { v: 2 * po * d0 + 2 * pi * (d1 + d3) + 2 * Tb * d2, t: '2(Pt−Qo)d0 + 2(Pt−Qi)(d1+d3) + 2Tb·d2' },
        { v: 2 * po * d0 + 2 * Tb * (d1 + d2 + d3), t: '2(Pt−Qo)d0 + 2Tb(d1+d2+d3)' },
        { v: 2 * pi * (d1 + d3) + 2 * Tb * (d0 + d2), t: '2(Pt−Qi)(d1+d3) + 2Tb(d0+d2)' },
        { v: 2 * Tb * (d0 + d1 + d2 + d3), t: '2Tb(d0+d1+d2+d3)' },
      ];
    } else {
      const ds = inner.reduce((x, y) => x + y, 0);
      cases = [
        { v: 2 * (Pt - Qi) * ds, t: '2(Pt−Qi)Σd' },
        { v: 2 * Tb * ds, t: '2Tb·Σd' },
      ];
    }
    // Qmax = NaN (căn âm) → bản phá hoại do uốn + cắt kết hợp: không có khả năng Mq
    const bad = isNaN(Qi) || (cfgExt && isNaN(Qo));
    let best = cases[0];
    cases.forEach((c) => { if (c.v > best.v) best = c; });
    return { Mnp, Mq: bad ? NaN : best.v, cases, best, sumD };
  }

  /* ---------------- Mô hình hình học ---------------- */
  function buildGeometry(inp) {
    const W = [];
    const beam = memberAtJoint(inp.beam, 'kèo');
    const col = memberAtJoint(inp.col, 'cột');
    const type = inp.type;
    const a = +inp.beam.slope || 0;
    const colInnerTilt = inp.col.innerStraight ? 0 : col.beta;   // độ nghiêng cánh trong cột
    const colOuterTilt = inp.col.innerStraight ? col.beta : 0;
    let M1, M2, thN, phiE, phiI, phiCE = null, phiCI = null;
    if (type === 'dung') {
      M1 = beam; M2 = col;
      thN = -colInnerTilt;                      // pháp tuyến bản (hướng vào kèo)
      phiE = fold(a - thN); phiI = fold(a + beam.beta - thN);
    } else if (type === 'ngang') {
      M1 = col; M2 = beam;
      thN = -90;                                 // bản nằm ngang, pháp tuyến hướng xuống cột
      phiE = fold(colOuterTilt); phiI = fold(colInnerTilt);
    } else {
      M1 = beam; M2 = col;
      const mode = inp.plate.mitre || 'bisector';
      thN = mode === 'bisector' ? (90 + a) / 2 : mode === 'perp' ? a + beam.beta / 2 : +inp.plate.theta;
      phiE = fold(a - thN); phiI = fold(a + beam.beta - thN);
      phiCE = fold(90 - colOuterTilt - thN); phiCI = fold(90 - colInnerTilt - thN);
    }
    [phiE, phiI].forEach((p) => { if (p > 60) throw new Error('Góc giữa cánh và pháp tuyến bản quá lớn (' + p.toFixed(1) + '°) — kiểm tra góc dốc / kiểu knee.'); });

    const pl = inp.plate;
    const cE = cosd(phiE), cI = cosd(phiI);
    const dp = M1.d / cE;                  // chiều cao tiết diện đo dọc bản
    const tfe = M1.tf / cE, tfi = M1.tf / cI;
    const dm = dp - tfe / 2 - tfi / 2;      // khoảng cách tâm 2 cánh dọc bản
    const phiA = (phiE + phiI) / 2;

    const rowsE = [], rowsI = [];
    if (pl.extE) rowsE.push({ s: -pl.pfoE, outer: true, grp: 'E' });
    for (let k = 0; k < pl.nE; k++) rowsE.push({ s: tfe + pl.pfiE + k * pl.pbE, outer: false, grp: 'E' });
    if (pl.extI) rowsI.push({ s: dp + pl.pfoI, outer: true, grp: 'I' });
    for (let k = 0; k < pl.nI; k++) rowsI.push({ s: dp - tfi - pl.pfiI - k * pl.pbI, outer: false, grp: 'I' });
    const sTop = pl.extE ? -(pl.pfoE + pl.Lev) : -pl.flushExt;
    const sBot = pl.extI ? dp + pl.pfoI + pl.Lev : dp + pl.flushExt;
    const bp = pl.g + 2 * pl.Leh;

    // Phía gối (M2) khi là bản đầu (knee xiên)
    let dpc = null, tfce = null, tfci = null, dmc = null;
    if (phiCE != null) {
      dpc = M2.d / cosd(phiCE); tfce = M2.tf / cosd(phiCE); tfci = M2.tf / cosd(phiCI);
      dmc = dpc - tfce / 2 - tfci / 2;
      if ((inp.sup.condE === 'endplate' || inp.sup.condI === 'endplate') && Math.abs(dpc - dp) / dp > 0.05)
        W.push('Knee xiên: chiều cao cột đo dọc bản (' + dpc.toFixed(0) + ' mm) lệch > 5% so với kèo (' + dp.toFixed(0) + ' mm) — vị trí cánh hai phía không trùng nhau, xem lại góc bản / tiết diện.');
    }
    return { W, type, beam, col, M1, M2, a, thN, phiE, phiI, phiA, phiCE, phiCI, dp, tfe, tfi, dm, rowsE, rowsI, sTop, sBot, bp, dpc, tfce, tfci, dmc, colInnerTilt, colOuterTilt };
  }

  /* ---------------- Phân tích tĩnh cho từng phía chịu kéo ---------------- */
  function sideStatic(G, inp, side, bolt) {
    const pl = inp.plate, sup = inp.sup;
    const T = side === 'E';
    const rows = (T ? G.rowsE : G.rowsI).map((r) => Object.assign({}, r));
    const ext = T ? pl.extE : pl.extI;
    const n = T ? pl.nE : pl.nI;
    const pfo = T ? pl.pfoE : pl.pfoI, pfi = T ? pl.pfiE : pl.pfiI, pb = T ? pl.pbE : pl.pbI;
    const compFace = T ? G.dp : 0;
    const compCtr = T ? G.dp - G.tfi / 2 : G.tfe / 2;
    rows.forEach((r) => { r.h = Math.abs(compFace - r.s); r.d = Math.abs(compCtr - r.s); });
    const outer = rows.find((r) => r.outer) || null;
    const inner = rows.filter((r) => !r.outer);
    const W = [];
    let stiff = !!(T ? pl.stiffE && pl.stiffE.on : pl.stiffI && pl.stiffI.on) && ext;
    let cfg;
    if (ext) {
      cfg = n === 1 ? (stiff ? '4ES' : '4E') : n === 2 ? 'MRE 1/2' : n === 3 ? 'MRE 1/3' : null;
      if (stiff && n > 1) { W.push('Sườn bản đầu chỉ hỗ trợ cho cấu hình 4ES — bỏ qua sườn với ' + cfg + '.'); stiff = false; }
    } else {
      cfg = n === 1 ? '2FU' : n === 2 ? '4FU' : null;
    }
    if (!cfg) throw new Error('Nhóm bu lông ' + (T ? 'cánh ngoài' : 'cánh trong') + ': cấu hình không hỗ trợ (flush tối đa 2 hàng, extended tối đa 3 hàng trong).');

    const gam = ext ? 1.0 : 1.25;
    const Fpy = G.plMat.Fy;
    const bpE = Math.min(G.bp, G.M1.bf + IN);
    const Yr = endPlateY(cfg, { bp: bpE, g: pl.g, pfi, pfo, pb, h0: outer ? outer.h : 0, h: inner.map((r) => r.h), de: pl.Lev });
    const phiMpl = 0.9 * Fpy * pl.tp * pl.tp * Yr.Y;
    const ken = kennedy({ t: pl.tp, Fy: Fpy, b: bpE, db: bolt.db, Fnt: bolt.Fnt, pfi, pfo: ext ? pfo : null, edgeOut: pl.Lev });
    const bm = boltMoments(ext, { d0: outer ? outer.d : null, inner: inner.map((r) => r.d) }, bolt.Pt, bolt.Tb, ken.Qi, ken.Qo);
    const phiMnp = 0.75 * bm.Mnp, phiMq = 0.75 * bm.Mq;
    const thick = phiMnp < 0.9 * phiMpl;

    // ---- Phía gối
    const cond = T ? sup.condE : sup.condI;
    const ts = sup.useFlange ? G.M2.tf : sup.t;
    const bs = sup.useFlange ? G.M2.bf : sup.b;
    const sMat = sup.useFlange ? G.M2.mat : G.supMat;
    let S = { cond, ts, bs, mat: sMat };
    if (cond === 'endplate') {
      const bsE = Math.min(bs, G.M2.bf + IN);
      const Ys = endPlateY(cfg, { bp: bsE, g: pl.g, pfi, pfo, pb, h0: outer ? outer.h : 0, h: inner.map((r) => r.h), de: pl.Lev });
      S.Y = Ys; S.bEff = bsE;
      S.phiM = 0.9 * sMat.Fy * ts * ts * Ys.Y / gam;
      S.ref = 'DG16 Sec 2.5';
    } else {
      const fc = T ? G.tfe / 2 : G.dp - G.tfi / 2;        // tâm cánh chịu kéo (vị trí sườn)
      const stS = T ? sup.stE : sup.stI;
      const tst = stS && stS.on ? stS.ts : 0;
      const innerRow = inner[0];
      const psiRaw = Math.abs(innerRow.s - fc) - tst / 2;
      const psoRaw = outer ? Math.abs(outer.s - fc) - tst / 2 : psiRaw;
      const sEnd = G.sTop - (+sup.topOffset || 0);        // đỉnh cấu kiện gối (dọc bản)
      const nearest = rows.slice().sort((x, y) => Math.abs(x.s - sEnd) - Math.abs(y.s - sEnd))[0];
      const pcpRaw = Math.abs(nearest.s - (sEnd + (+sup.tcap || 0)));
      const de = Math.abs(nearest.s - sEnd);
      if (cond === 'cont_stiff' && !(stS && stS.on)) W.push('Chọn "cột liên tục có sườn" nhưng chưa khai báo sườn ngang tại cánh ' + (T ? 'ngoài' : 'trong') + '.');
      const Ys = supportYc(cond, { b: bs, g: pl.g, rows, psiRaw: T && !outer ? psiRaw : psiRaw, psoRaw, pcpRaw, de, stiffBetween: !!outer });
      if (Ys.note) W.push(Ys.note);
      S.Y = Ys; S.bEff = bs;
      S.phiM = 0.9 * sMat.Fy * ts * ts * Ys.Y;
      S.ref = 'DG4 Eq. 3.21';
    }
    S.ken = kennedy({ t: ts, Fy: sMat.Fy, b: S.bEff, db: bolt.db, Fnt: bolt.Fnt, pfi, pfo: ext ? pfo : null, edgeOut: pl.Lev });
    S.bm = boltMoments(ext, { d0: outer ? outer.d : null, inner: inner.map((r) => r.d) }, bolt.Pt, bolt.Tb, S.ken.Qi, S.ken.Qo);
    S.phiMq = 0.75 * S.bm.Mq;
    S.thick = phiMnp < 0.9 * S.phiM * (cond === 'endplate' ? gam : 1);

    return { side, T, cfg, ext, n, rows, outer, inner, pfo, pfi, pb, gam, Fpy, bpE, Yr, phiMpl, ken, bm, phiMnp, phiMq, thick, stiff, S, W };
  }

  /* ---------------- Tiện ích ---------------- */
  const kN = (x) => x / 1e3;
  const kNm = (x) => x / 1e6;
  const f1 = (x) => (x == null || isNaN(x) ? '—' : Number(x).toFixed(1));
  const f2 = (x) => (x == null || isNaN(x) ? '—' : Number(x).toFixed(2));
  const f3 = (x) => (x == null || isNaN(x) ? '—' : Number(x).toFixed(3));

  /* =====================================================================
   * TÍNH TOÁN CHÍNH
   * ===================================================================== */
  function compute(inp) {
    const G = buildGeometry(inp);
    const W = G.W;
    const pl = inp.plate, sup = inp.sup;
    G.plMat = material(pl.mat, pl.matCustom);
    G.supMat = material(sup.mat, sup.matCustom);
    const bg = BOLT_GRADES[inp.bolt.grade] || BOLT_GRADES['8.8'];
    const db = +inp.bolt.d;
    const Ab = Math.PI * db * db / 4;
    let Tb = (PRETENSION[bg.pre][db] || 0.7 * bg.Fnt / 0.75 * 0.7 * Ab / 1e3) * 1e3;
    let snugF = 1;
    if (inp.bolt.snug) {
      snugF = db <= 16 ? 0.75 : db <= 20 ? 0.5 : db <= 22 ? 0.375 : 0.25;
      Tb *= snugF;
      if (bg.pre === 'A490') W.push('Bu lông cường độ cao cấp A490/10.9 không được phép siết sơ bộ (snug-tight) theo RCSC — DG16 §2.5.3.');
    }
    const bolt = { grade: inp.bolt.grade, bg, db, Ab, Fnt: bg.Fnt, Fnv: inp.bolt.thread === 'X' ? bg.FnvX : bg.FnvN, Pt: bg.Fnt * Ab, Tb, snugF, dh: holeDia(db) };
    G.bolt = bolt;
    const weldF = ELECTRODES[inp.weld.electrode] || 482.6;
    const dirFactor = inp.opt.directional ? 1.5 : 1.0;

    const sides = {};
    ['E', 'I'].forEach((sd) => {
      try { sides[sd] = sideStatic(G, inp, sd, bolt); sides[sd].W.forEach((w) => W.push(w)); }
      catch (e) { sides[sd] = { error: e.message }; W.push(e.message); }
    });

    const checks = {};
    const order = [];
    function add(id, grp, name, unit, ref, cap, dem, combo, detail, tags, info) {
      const ratio = cap > 0 ? Math.abs(dem) / cap : (dem > 0 ? Infinity : 0);
      let c = checks[id];
      if (!c) { c = checks[id] = { id, grp, name, unit, ref, cap, dem, ratio: -1, combo, detail: [], tags: tags || [], info: !!info }; order.push(id); }
      if (ratio > c.ratio || isNaN(ratio)) {
        Object.assign(c, { cap, dem, ratio: isNaN(ratio) ? Infinity : ratio, combo, detail: typeof detail === 'function' ? detail() : detail || [] });
      }
    }

    const combos = (inp.loads || []).filter((l) => l && l.name !== undefined);
    const demands = [];
    const M1 = G.M1, M2 = G.M2;
    const tp = pl.tp;
    const Fpu = G.plMat.Fu;
    const phiA = G.phiA;

    // Tĩnh: bảng bu lông cho nhóm
    const nBoltsE = 2 * G.rowsE.length, nBoltsI = 2 * G.rowsI.length;

    // Ép mặt: tính cho từng hàng của nhóm, hai chiều lực cắt → lấy chiều bất lợi
    function bearingGroup(rows, allRows, t, Fu, sLo, sHi) {
      const s = allRows.map((r) => r.s).sort((a, b) => a - b);
      let total = 0; const lines = [];
      rows.forEach((r) => {
        const idx = s.indexOf(r.s);
        const up = idx > 0 ? s[idx] - s[idx - 1] - bolt.dh : r.s - sLo - bolt.dh / 2;
        const dn = idx < s.length - 1 ? s[idx + 1] - s[idx] - bolt.dh : sHi - r.s - bolt.dh / 2;
        const lc = Math.max(Math.min(up, dn), 0);
        const rn = Math.min(1.2 * lc * t * Fu, 2.4 * db * t * Fu);
        total += 2 * rn;
        lines.push('Hàng s = ' + f1(r.s) + ' mm: lc = ' + f1(lc) + ' mm → Rn/bu lông = min(1.2·lc·t·Fu; 2.4·d·t·Fu) = ' + f1(kN(rn)) + ' kN');
      });
      return { phiRn: 0.75 * total, lines };
    }
    const allRows = G.rowsE.concat(G.rowsI);
    const tsSup = sup.useFlange ? M2.tf : sup.t;
    const supMatEff = sup.useFlange ? M2.mat : G.supMat;
    const bearE_p = bearingGroup(G.rowsE, allRows, tp, Fpu, G.sTop, G.sBot), bearI_p = bearingGroup(G.rowsI, allRows, tp, Fpu, G.sTop, G.sBot);
    // Bản gối: nếu là cánh cấu kiện liên tục → không có mép tự do (trừ đầu cấu kiện khi điều kiện "đỉnh")
    let sLoS = G.sTop, sHiS = G.sBot;
    if (sup.useFlange) {
      const topC = /^top_/.test(sup.condE) || /^top_/.test(sup.condI);
      sLoS = topC ? G.sTop - (+sup.topOffset || 0) : -1e9;
      sHiS = 1e9;
    }
    const bearE_s = bearingGroup(G.rowsE, allRows, tsSup, supMatEff.Fu, sLoS, sHiS), bearI_s = bearingGroup(G.rowsI, allRows, tsSup, supMatEff.Fu, sLoS, sHiS);

    // J10 (phía gối là cánh + bụng cấu kiện M2)
    const flangeSupport = (G.type !== 'xien') || (sup.condE !== 'endplate' && sup.condI !== 'endplate');
    const tf2 = sup.useFlange ? M2.tf : Math.max(M2.tf, sup.t);
    const k2 = tf2 + (+sup.kw || 0);
    const h2 = M2.d - 2 * M2.tf;
    const tw2 = M2.tw;
    const Fy2 = M2.mat.Fy;
    const sEnd = G.sTop - (+sup.topOffset || 0);
    const fcE = G.tfe / 2, fcI = G.dp - G.tfi / 2;
    function flangeFacts(f) {
      const wfl = f === 'E' ? inp.weld.flE : inp.weld.flI;
      const tfp = f === 'E' ? G.tfe : G.tfi;
      const N = tfp + (wfl.type === 'fillet' ? 2 * wfl.w : 0);
      const dist = (f === 'E' ? fcE : fcI) - sEnd;
      return { N, dist, tfp };
    }
    function webYield(f) {
      const { N, dist } = flangeFacts(f);
      const Ct = dist < M2.d ? 0.5 : 1.0;
      const Rn = Ct * (6 * k2 + N + 2 * tp) * Fy2 * tw2;
      return { phiRn: 1.0 * Rn, Ct, N, dist, txt: 'φRn = φ·Ct·(6k + N + 2tp)·Fy·tw = 1.0·' + Ct + '·(6·' + f1(k2) + ' + ' + f1(N) + ' + 2·' + f1(tp) + ')·' + Fy2 + '·' + f1(tw2) };
    }
    function webCrip(f) {
      const { N, dist } = flangeFacts(f);
      const r = Math.pow(tw2 / tf2, 1.5);
      const root = Math.sqrt(E * Fy2 * tf2 / tw2);
      let Rn, t;
      if (dist >= M2.d / 2) { Rn = 0.80 * tw2 * tw2 * (1 + 3 * (N / M2.d) * r) * root; t = '0.80·tw²·[1 + 3(N/d)(tw/tf)^1.5]·√(E·Fy·tf/tw)  (J10-4)'; }
      else if (N / M2.d <= 0.2) { Rn = 0.40 * tw2 * tw2 * (1 + 3 * (N / M2.d) * r) * root; t = '0.40·tw²·[1 + 3(N/d)(tw/tf)^1.5]·√(E·Fy·tf/tw)  (J10-5a)'; }
      else { Rn = 0.40 * tw2 * tw2 * (1 + (4 * N / M2.d - 0.2) * r) * root; t = '0.40·tw²·[1 + (4N/d − 0.2)(tw/tf)^1.5]·√(E·Fy·tf/tw)  (J10-5b)'; }
      return { phiRn: 0.75 * Rn, txt: 'φRn = 0.75·' + t };
    }
    function webBuck(f) {
      const { dist } = flangeFacts(f);
      const coef = dist >= M2.d / 2 ? 24 : 12;
      const Rn = coef * Math.pow(tw2, 3) * Math.sqrt(E * Fy2) / h2;
      return { phiRn: 0.9 * Rn, txt: 'φRn = 0.9·' + coef + '·tw³·√(E·Fy)/h  (J10-8' + (coef === 12 ? ', gần đầu cấu kiện ×0.5' : '') + '), h = ' + f1(h2) };
    }

    // Sườn ngang phía gối
    function stiffCap(f) {
      const st = f === 'E' ? sup.stE : sup.stI;
      if (!st || !st.on) return null;
      const stMat = material(st.mat, st.matCustom);
      const bn = st.bs - st.clip;
      const Ast = 2 * bn * st.ts;
      const phiT = 0.9 * stMat.Fy * Ast;
      // nén: J10.8 — cột gồm 2 sườn + 25tw bụng (12tw nếu gần đầu)
      const { dist } = flangeFacts(f);
      const Lw = (dist < M2.d ? 12 : 25) * tw2;
      const A = 2 * st.bs * st.ts + Lw * tw2;
      const I = st.ts * Math.pow(2 * st.bs + tw2, 3) / 12;
      const r = Math.sqrt(I / A);
      const KL = 0.75 * h2;
      const lam = KL / r;
      let Pn, pt;
      if (lam <= 25) { Pn = Math.min(stMat.Fy, Fy2) * A; pt = 'KL/r = ' + f1(lam) + ' ≤ 25 → Pn = Fy·A (J4.4)'; }
      else {
        const Fe = Math.PI * Math.PI * E / (lam * lam);
        const Fy = Math.min(stMat.Fy, Fy2);
        const Fcr = lam <= 4.71 * Math.sqrt(E / Fy) ? Math.pow(0.658, Fy / Fe) * Fy : 0.877 * Fe;
        Pn = Fcr * A; pt = 'KL/r = ' + f1(lam) + ' > 25 → Fcr theo E3 = ' + f1(Fcr) + ' MPa';
      }
      const phiC = 0.9 * Pn;
      const wf = st.wf, ww = st.ww;
      const qf = 0.75 * 0.6 * weldF * 0.707 * wf * dirFactor;          // N/mm mỗi đường
      const phiWF = qf * 2 * 2 * bn;
      const Lst = st.fullDepth ? h2 : h2 / 2;
      const qw = 0.75 * 0.6 * weldF * 0.707 * ww;
      const phiWW = qw * 2 * 2 * Math.max(Lst - 2 * st.clip, 0);
      return { st, stMat, bn, Ast, phiT, phiC, pt, A, Lw, phiWF, phiWW, Lst };
    }

    // Panel zone
    const Ag2 = M2.A;
    const diag = sup.diag || {};

    // ====== duyệt tổ hợp ======
    combos.forEach((cb, ci) => {
      const isNgang = G.type === 'ngang';
      const N = (isNgang ? +cb.Nc : +cb.Nb) * 1e3;
      const V = (isNgang ? +cb.Vc : +cb.Vb) * 1e3;
      const M = (isNgang ? +cb.Mc : +cb.Mb) * 1e6;
      const N2 = (isNgang ? +cb.Nb : +cb.Nc) * 1e3;
      const V2 = (isNgang ? +cb.Vb : +cb.Vc) * 1e3;
      const nm = cb.name || ('TH' + (ci + 1));
      const Nn = N * cosd(phiA) + Math.abs(V) * sind(phiA);
      const Vt = Math.abs(N) * sind(phiA) + Math.abs(V) * cosd(phiA);
      const FnE = -M / G.dm + Nn / 2;
      const FnI = M / G.dm + Nn / 2;
      const Nrel = inp.opt.axialRelief ? Nn : Math.max(Nn, 0);
      const Mu = Math.max(Math.abs(M) + Nrel * G.dm / 2, 0);
      const side = M < 0 ? 'E' : M > 0 ? 'I' : null;
      const Vpz = Math.max(Math.abs(FnE), Math.abs(FnI)) - (inp.opt.pzSubtractShear ? Math.abs(V2) : 0);
      demands.push({ name: nm, V: kN(V), N: kN(N), M: kNm(M), Nn: kN(Nn), Vt: kN(Vt), FnE: kN(FnE), FnI: kN(FnI), Mu: kNm(Mu), side, Vpz: kN(Vpz), N2: kN(N2), V2: kN(V2) });

      // ---------- Bản đầu + bu lông (phía chịu kéo) ----------
      if (side && sides[side] && !sides[side].error) {
        const S = sides[side];
        const gname = side === 'E' ? 'Bản đầu — nhóm cánh ngoài' : 'Bản đầu — nhóm cánh trong';
        const tg = ['plate', 'bolts' + side];
        const common = () => [
          'Cấu hình: ' + S.cfg + ' (' + (S.ext ? 'extended' : 'flush') + '),  γr = ' + S.gam,
          'Mu,eq = |M| + Nn·dm/2 = ' + f2(kNm(Math.abs(M))) + ' + ' + f2(kN(Nrel)) + '·' + f1(G.dm) + '/2/1000 = ' + f2(kNm(Mu)) + ' kN·m',
          'Hàng bu lông kéo (h từ mặt ngoài cánh nén; d từ tâm cánh nén): ' + S.rows.map((r) => (r.outer ? 'ngoài' : 'trong') + ' h=' + f1(r.h) + ', d=' + f1(r.d)).join(' | '),
        ];
        add('pl_flex_' + side, gname, 'Chảy dẻo uốn bản đầu', 'kN·m', 'DG16 Sec 2.5', kNm(S.phiMpl / S.gam), kNm(Mu), nm, () => common().concat([
          'bp,eff = min(bp; bf + 25.4) = min(' + f1(G.bp) + '; ' + f1(M1.bf + IN) + ') = ' + f1(S.bpE) + ' mm,  s = ½√(bp·g) = ' + f1(S.Yr.s) + ' mm',
          S.Yr.formula,
          'Y = ' + f1(S.Yr.Y) + ' mm',
          'φb·Mpl = 0.9·Fpy·tp²·Y = 0.9·' + S.Fpy + '·' + tp + '²·' + f1(S.Yr.Y) + ' = ' + f2(kNm(S.phiMpl)) + ' kN·m',
          'Khả năng = φb·Mpl/γr = ' + f2(kNm(S.phiMpl / S.gam)) + ' kN·m',
          'Ứng xử bản: ' + (S.thick ? 'BẢN DÀY (φMnp < 0.9φbMpl) — không nhổ' : 'BẢN MỎNG (φMnp ≥ 0.9φbMpl) — có lực nhổ'),
          'tp,req (bản mỏng) = √(γr·Mu/(φb·Fpy·Y)) = ' + f1(Math.sqrt(S.gam * Mu / (0.9 * S.Fpy * S.Yr.Y))) + ' mm',
        ]), tg);
        add('bolt_np_' + side, gname, 'Đứt bu lông không nhổ (φMnp)', 'kN·m', 'DG16 Sec 2.5 / DG4 Eq. 3.7', kNm(S.phiMnp), kNm(Mu), nm, () => common().concat([
          'Pt = Fnt·Ab = ' + bg.Fnt + '·' + f1(Ab) + ' = ' + f1(kN(bolt.Pt)) + ' kN',
          'Σd = ' + f1(S.bm.sumD) + ' mm',
          'φMnp = 0.75·2·Pt·Σd = ' + f2(kNm(S.phiMnp)) + ' kN·m',
          'db,req = √(2Mu/(π·φ·Fnt·Σd)) = ' + f1(Math.sqrt(2 * Mu / (Math.PI * 0.75 * bolt.Fnt * S.bm.sumD))) + ' mm',
        ]), ['bolts' + side]);
        add('bolt_q_' + side, gname, 'Đứt bu lông có lực nhổ (φMq)', 'kN·m', 'DG16 Sec 2.5 (Kennedy hiệu chỉnh)', kNm(S.phiMq), kNm(Mu), nm, () => common().concat([
          'w\' = bp/2 − (db + 1/16") = ' + f1(S.ken.wc) + ' mm;  ai = 3.682(tp/db)³ − 0.085 [in] = ' + f2(S.ken.a) + ' mm',
          'F\'i = [tp²·Fpy(0.85bp/2 + 0.8w\') + π·db³·Fnt/8]/(4pf,i) = ' + f1(kN(S.ken.Fi)) + ' kN',
          'Qmax,i = w\'tp²/(4ai)·√(Fpy² − 3(F\'i/(w\'tp))²) = ' + f1(kN(S.ken.Qi)) + ' kN',
          S.ext ? ('ao = min(ai; pext − pf,o) = ' + f2(S.ken.ao) + ' mm;  F\'o = F\'i·pf,i/pf,o = ' + f1(kN(S.ken.Fo)) + ' kN;  Qmax,o = ' + f1(kN(S.ken.Qo)) + ' kN') : 'Flush: không có hàng ngoài',
          'Pt = ' + f1(kN(bolt.Pt)) + ' kN;  Tb = ' + f1(kN(bolt.Tb)) + ' kN' + (inp.bolt.snug ? ' (siết sơ bộ ×' + bolt.snugF + ')' : ''),
        ]).concat(S.bm.cases.map((c) => '  ' + c.t + ' = ' + f2(kNm(c.v)) + ' kN·m')).concat([
          'φMq = 0.75·max(...) = ' + f2(kNm(S.phiMq)) + ' kN·m' + (isNaN(S.phiMq) ? '  → căn âm: bản bị phá hoại do uốn + cắt kết hợp, cần tăng tp' : ''),
        ]), ['bolts' + side, 'plate']);

        // phía gối
        const Sg = S.S;
        const sgname = 'Phía gối (' + (G.type === 'ngang' ? 'kèo' : 'cột') + ') — ' + (side === 'E' ? 'cánh ngoài' : 'cánh trong');
        add('sup_flex_' + side, sgname, Sg.cond === 'endplate' ? 'Chảy dẻo uốn bản đầu cột' : 'Chảy dẻo uốn cánh/bản gối', 'kN·m', Sg.ref, kNm(Sg.phiM), kNm(Mu), nm, () => [
          'Điều kiện: ' + condLabel(Sg.cond) + ';  t = ' + f1(Sg.ts) + ' mm; b = ' + f1(Sg.bEff) + ' mm; Fy = ' + Sg.mat.Fy + ' MPa',
          Sg.Y.formula, 'Y = ' + f1(Sg.Y.Y) + ' mm',
          Sg.cond === 'endplate' ? ('φMpl/γr = 0.9·Fy·t²·Y/γr = ' + f2(kNm(Sg.phiM)) + ' kN·m') : ('φMcf = 0.9·Fyc·tcf²·Yc = ' + f2(kNm(Sg.phiM)) + ' kN·m'),
          'Mu,eq = ' + f2(kNm(Mu)) + ' kN·m',
        ], ['support' + side]);
        add('sup_q_' + side, sgname, 'Đứt bu lông có lực nhổ (phía gối)', 'kN·m', 'DG16 Sec 2.5', kNm(Sg.phiMq), kNm(Mu), nm, () => [
          't = ' + f1(Sg.ts) + ' mm, b = ' + f1(Sg.bEff) + ' mm, Fy = ' + Sg.mat.Fy,
          'Qmax,i = ' + f1(kN(Sg.ken.Qi)) + ' kN' + (S.ext ? ';  Qmax,o = ' + f1(kN(Sg.ken.Qo)) + ' kN' : ''),
        ].concat(Sg.bm.cases.map((c) => '  ' + c.t + ' = ' + f2(kNm(c.v)) + ' kN·m')).concat(['φMq = ' + f2(kNm(Sg.phiMq)) + ' kN·m']), ['support' + side, 'bolts' + side]);

        // Bu lông kéo tuyệt đối không vượt Pt: đã nằm trong Mnp
      }

      // ---------- Cắt / ép mặt bu lông ----------
      {
        const grp = side === 'E' ? 'I' : side === 'I' ? 'E' : 'A';
        const nB = inp.opt.shearAll || grp === 'A' ? nBoltsE + nBoltsI : grp === 'E' ? nBoltsE : nBoltsI;
        const phiRv = 0.75 * bolt.Fnv * Ab * nB;
        const gn = inp.opt.shearAll || grp === 'A' ? 'Bu lông (toàn bộ)' : grp === 'E' ? 'Bản đầu — nhóm cánh ngoài' : 'Bản đầu — nhóm cánh trong';
        const idg = inp.opt.shearAll || grp === 'A' ? 'A' : grp;
        add('bolt_v_' + idg, gn, 'Bu lông chịu cắt', 'kN', 'AISC J3.6 (Table J3.2)', kN(phiRv), kN(Vt), nm, () => [
          'Lực cắt dọc bản Vt = |N|·sinφ + |V|·cosφ = ' + f2(kN(Vt)) + ' kN  (φ = ' + f1(phiA) + '°)',
          'Bu lông chịu cắt: ' + (inp.opt.shearAll ? 'toàn bộ' : 'nhóm phía nén') + ', n = ' + nB,
          'φRn = 0.75·Fnv·Ab·n = 0.75·' + f1(bolt.Fnv) + '·' + f1(Ab) + '·' + nB + ' = ' + f2(kN(phiRv)) + ' kN',
        ], ['bolts' + (idg === 'A' ? 'E' : idg), 'bolts' + (idg === 'A' ? 'I' : idg)]);
        const useE = idg === 'E' || idg === 'A', useI = idg === 'I' || idg === 'A';
        const capP = (useE ? bearE_p.phiRn : 0) + (useI ? bearI_p.phiRn : 0);
        const capS = (useE ? bearE_s.phiRn : 0) + (useI ? bearI_s.phiRn : 0);
        add('bear_p_' + idg, gn, 'Ép mặt / xé bu lông trên bản đầu', 'kN', 'AISC Eq. J3-6', kN(capP), kN(Vt), nm, () => ['t = tp = ' + tp + ' mm, Fu = ' + Fpu + ' MPa (lc lấy theo chiều bất lợi)']
          .concat(useE ? bearE_p.lines : []).concat(useI ? bearI_p.lines : []).concat(['φRn = 0.75·Σ(2·Rn) = ' + f2(kN(capP)) + ' kN']), ['plate']);
        add('bear_s_' + idg, gn.replace('Bản đầu', 'Phía gối'), 'Ép mặt / xé bu lông trên bản gối', 'kN', 'AISC Eq. J3-6', kN(capS), kN(Vt), nm, () => ['t = ' + tsSup + ' mm, Fu = ' + supMatEff.Fu + ' MPa']
          .concat(useE ? bearE_s.lines : []).concat(useI ? bearI_s.lines : []).concat(['φRn = ' + f2(kN(capS)) + ' kN']), ['supportE', 'supportI']);
      }

      // ---------- Cắt bản đầu tại cánh (DG4 Eq. 3.12, 3.13) ----------
      ['E', 'I'].forEach((f) => {
        const Fn = f === 'E' ? FnE : FnI;
        const gname = f === 'E' ? 'Bản đầu — nhóm cánh ngoài' : 'Bản đầu — nhóm cánh trong';
        const Rv = 0.9 * 0.6 * G.plMat.Fy * G.bp * tp;
        add('pl_vy_' + f, gname, 'Cắt chảy bản đầu (Ffu/2)', 'kN', 'DG4 Eq. 3.12', kN(Rv), kN(Math.abs(Fn) / 2), nm, () => [
          'Ffu = |M|/dm ± Nn/2 = ' + f2(kN(Math.abs(Fn))) + ' kN',
          'φRn = 0.9·0.6·Fpy·bp·tp = 0.9·0.6·' + G.plMat.Fy + '·' + f1(G.bp) + '·' + tp + ' = ' + f2(kN(Rv)) + ' kN',
        ], ['plate']);
        const extF = f === 'E' ? pl.extE : pl.extI;
        if (extF && Fn > 0 && !(f === 'E' ? sides.E.stiff : sides.I.stiff)) {
          const An = (G.bp - 2 * (bolt.dh + 2)) * tp;
          const Rr = 0.75 * 0.6 * Fpu * An;
          add('pl_vr_' + f, gname, 'Cắt đứt phần bản nhô (Ffu/2)', 'kN', 'DG4 Eq. 3.13', kN(Rr), kN(Fn / 2), nm, () => [
            'An = [bp − 2(dh + 2)]·tp = [' + f1(G.bp) + ' − 2(' + bolt.dh + ' + 2)]·' + tp + ' = ' + f1(An) + ' mm²',
            'φRn = 0.75·0.6·Fpu·An = ' + f2(kN(Rr)) + ' kN',
          ], ['plate']);
        }
      });

      // ---------- Hàn & bụng cấu kiện M1 ----------
      function memberWelds(mem, key, dmL, FE, FI, phE, phI, dpL, tfeL, tfiL, label, tagm) {
        const wcfg = inp.weld;
        ['E', 'I'].forEach((f) => {
          const Fn = f === 'E' ? FE : FI;
          if (Fn <= 0) return;
          const ph = f === 'E' ? phE : phI;
          const w = f === 'E' ? wcfg.flE : wcfg.flI;
          let Ff = Fn / cosd(ph);
          const Fmin = 0.6 * mem.mat.Fy * mem.bf * mem.tf;
          if (inp.opt.flangeWeldMin) Ff = Math.max(Ff, Fmin);
          const nm2 = 'Hàn cánh ' + (f === 'E' ? 'ngoài' : 'trong') + ' — bản đầu';
          if (w.type === 'cjp') {
            const cap = 0.9 * mem.mat.Fy * mem.bf * mem.tf;
            add(key + '_wf_' + f, label, nm2 + ' (CJP)', 'kN', 'AISC Table J2.5 / J4.1', kN(cap), kN(Ff), nm, () => [
              'Hàn thấu CJP: khả năng = φ·Fy·bf·tf = 0.9·' + mem.mat.Fy + '·' + mem.bf + '·' + mem.tf + ' = ' + f2(kN(cap)) + ' kN',
              'Lực cánh theo phương cánh = Fn/cosφ = ' + f2(kN(Fn)) + '/cos' + f1(ph) + '° = ' + f2(kN(Fn / cosd(ph))) + ' kN' + (inp.opt.flangeWeldMin ? ' (≥ 0.6FyAf = ' + f2(kN(Fmin)) + ')' : ''),
            ], [tagm + 'weld' + f]);
          } else {
            const Lw = 2 * mem.bf - mem.tw;
            const cap = 0.75 * 0.6 * weldF * dirFactor * 0.707 * w.w * Lw;
            add(key + '_wf_' + f, label, nm2 + ' (hàn góc)', 'kN', 'AISC Eq. J2-4, J2-5', kN(cap), kN(Ff), nm, () => [
              'Lw = 2bf − tw = ' + f1(Lw) + ' mm;  w = ' + w.w + ' mm (' + f1(w.w / IN * 16) + '/16"),  FEXX = ' + weldF + ' MPa',
              'φRn = 0.75·0.6·FEXX·' + dirFactor + '·0.707·w·Lw = ' + f2(kN(cap)) + ' kN',
              'Lực cánh theo phương cánh = Fn/cosφ = ' + f2(kN(Ff)) + ' kN',
            ], [tagm + 'weld' + f]);
          }
        });
        const ww = inp.weld.web.w;
        const qdem = 0.9 * mem.mat.Fy * mem.tw;          // N/mm — phát triển chảy bụng (DG16 §2.5.3 item 9)
        const qcap = 2 * 0.75 * 0.6 * weldF * 0.707 * ww * dirFactor;
        if (Math.abs(M) > 0)
          add(key + '_ww_t', label, 'Hàn bụng vùng kéo (phát triển chảy bụng)', 'kN/m', 'AISC Eq. J2-4; J4-1', qcap, qdem, nm, () => [
            'Yêu cầu = φ·Fy·tw = 0.9·' + mem.mat.Fy + '·' + mem.tw + ' = ' + f1(qdem) + ' N/mm (kN/m)',
            'Khả năng 2 đường hàn góc: 2·0.75·0.6·FEXX·0.707·w·' + dirFactor + ' = ' + f1(qcap) + ' N/mm',
          ], [tagm + 'webweld']);
        // hàn bụng chịu cắt
        const sd = side || 'E';
        const Sx = sides[sd] && !sides[sd].error ? sides[sd] : null;
        let Lws = dpL / 2 - (sd === 'E' ? tfiL : tfeL);
        if (Sx) {
          const innerLast = Sx.inner[Sx.inner.length - 1];
          const compInner = sd === 'E' ? dpL - tfiL : tfeL;
          Lws = Math.min(Lws, Math.abs(compInner - innerLast.s) - 2 * db);
        }
        Lws = Math.max(Lws, 0);
        const capV = 2 * 0.75 * 0.6 * weldF * 0.707 * ww * Lws;
        add(key + '_ww_v', label, 'Hàn bụng chịu cắt', 'kN', 'AISC Eq. J2-4', kN(capV), kN(Vt), nm, () => [
          'Chiều dài hàn hiệu quả (DG16 §2.5.3 item 10): min(d/2 − tf,c ; khoảng từ hàng kéo trong + 2db tới cánh nén) = ' + f1(Lws) + ' mm',
          'φRn = 2·0.75·0.6·FEXX·0.707·w·L = ' + f2(kN(capV)) + ' kN',
        ], [tagm + 'webweld']);
        const capWV = 1.0 * 0.6 * mem.mat.Fy * dpL * mem.tw;
        add(key + '_wv', label, 'Chảy cắt bụng ' + (key === 'm1' ? 'cấu kiện' : 'cột') + ' tại bản', 'kN', 'AISC Eq. J4-3', kN(capWV), kN(Vt), nm, () => [
          'φRn = 1.0·0.6·Fy·d·tw = 0.6·' + mem.mat.Fy + '·' + f1(dpL) + '·' + mem.tw + ' = ' + f2(kN(capWV)) + ' kN',
        ], [tagm + 'web']);
      }
      memberWelds(M1, 'm1', G.dm, FnE, FnI, G.phiE, G.phiI, G.dp, G.tfe, G.tfi, (G.type === 'ngang' ? 'Cột' : 'Kèo') + ' (cấu kiện có bản đầu)', 'm1');
      if (G.type === 'xien' && (sup.condE === 'endplate' || sup.condI === 'endplate')) {
        const FcE = -M / G.dmc + Nn / 2, FcI = M / G.dmc + Nn / 2;
        memberWelds(M2, 'm2', G.dmc, FcE, FcI, G.phiCE, G.phiCI, G.dpc, G.tfce, G.tfci, 'Cột (bản đầu phía cột)', 'm2');
      }

      // ---------- J10 phía gối, panel, sườn ----------
      if (flangeSupport) {
        const glab = 'Bụng cấu kiện gối (' + (G.type === 'ngang' ? 'kèo' : 'cột') + ')';
        ['E', 'I'].forEach((f) => {
          const Fn = f === 'E' ? FnE : FnI;
          const Fa = Math.abs(Fn);
          if (Fa <= 0) return;
          const stc = stiffCap(f);
          const fl = f === 'E' ? 'cánh ngoài' : 'cánh trong';
          const wy = webYield(f);
          const caps = [{ n: 'chảy cục bộ bụng', v: wy.phiRn }];
          add('j10y_' + f, glab, 'Chảy cục bộ bụng tại ' + fl, 'kN', 'AISC J10.2 / DG4 Eq. 3.24', kN(wy.phiRn), kN(Fa), nm, () => [
            'Khoảng cách tới đầu cấu kiện = ' + f1(wy.dist) + ' mm → Ct = ' + wy.Ct + ';  k = tf + hàn = ' + f1(k2) + ' mm;  N = ' + f1(wy.N) + ' mm',
            wy.txt + ' = ' + f2(kN(wy.phiRn)) + ' kN',
            'Lực cánh Ffu = ' + f2(kN(Fa)) + ' kN' + (stc ? '  (có sườn → kiểm tra sườn bên dưới)' : ''),
          ], ['sup' + f + 'web'], !!stc);
          if (Fn < 0) {
            const wc = webCrip(f), wb = webBuck(f);
            caps.push({ n: 'oằn nhàu', v: wc.phiRn }, { n: 'oằn nén bụng', v: wb.phiRn });
            add('j10c_' + f, glab, 'Oằn nhàu bụng tại ' + fl + ' (nén)', 'kN', 'AISC J10.3 / DG4 Eq. 3.29–3.31', kN(wc.phiRn), kN(Fa), nm, () => [wc.txt, '= ' + f2(kN(wc.phiRn)) + ' kN'], ['sup' + f + 'web'], !!stc);
            if (inp.opt.webBuckling)
              add('j10b_' + f, glab, 'Oằn nén bụng tại ' + fl + ' (nén)', 'kN', 'AISC J10.5 / DG4 Eq. 3.26', kN(wb.phiRn), kN(Fa), nm, () => [wb.txt, '= ' + f2(kN(wb.phiRn)) + ' kN'], ['sup' + f + 'web'], !!stc);
          } else if (sides[f] && !sides[f].error && side === f) {
            const Sx = sides[f];
            if (Sx.S.cond !== 'endplate') caps.push({ n: 'uốn cánh gối', v: Sx.S.phiM / (G.dm) });
          }
          const minCap = caps.reduce((x, y) => (y.v < x.v ? y : x));
          const Fsu = Math.max(Fa - minCap.v, 0);
          if (stc) {
            const sn = 'Sườn ngang gối tại ' + fl;
            const capAx = Fn < 0 ? stc.phiC : stc.phiT;
            add('st_ax_' + f, sn, Fn < 0 ? 'Sườn chịu nén (J10.8 + J4.4)' : 'Sườn chịu kéo — chảy (J4.1)', 'kN', Fn < 0 ? 'AISC J10.8, J4.4' : 'AISC Eq. J4-1', kN(capAx), kN(Fsu), nm, () => [
              'Fsu = Ffu − min(φRn) = ' + f2(kN(Fa)) + ' − ' + f2(kN(minCap.v)) + ' (' + minCap.n + ') = ' + f2(kN(Fsu)) + ' kN   (DG4 Eq. 3.32)',
              'Sườn: 2 × ' + stc.st.bs + '×' + stc.st.ts + ' mm, vát góc ' + stc.st.clip + ' mm, ' + stc.stMat.name,
              Fn < 0 ? (stc.pt + ';  A = 2bs·ts + ' + (stc.Lw / tw2).toFixed(0) + 'tw·tw = ' + f1(stc.A) + ' mm² → φPn = ' + f2(kN(stc.phiC)) + ' kN') : ('φRn = 0.9·Fy·Ast = 0.9·' + stc.stMat.Fy + '·' + f1(stc.Ast) + ' = ' + f2(kN(stc.phiT)) + ' kN'),
            ], ['sup' + f + 'stiff']);
            add('st_wf_' + f, sn, 'Hàn sườn – cánh', 'kN', 'AISC Eq. J2-4', kN(stc.phiWF), kN(Fsu), nm, () => [
              '4 đường hàn góc w = ' + stc.st.wf + ' mm, L = bs − clip = ' + f1(stc.bn) + ' mm → φRn = ' + f2(kN(stc.phiWF)) + ' kN',
            ], ['sup' + f + 'stiff']);
            add('st_ww_' + f, sn, 'Hàn sườn – bụng', 'kN', 'AISC Eq. J2-4', kN(stc.phiWW), kN(Fsu), nm, () => [
              '4 đường hàn góc w = ' + stc.st.ww + ' mm, L = ' + f1(stc.Lst) + ' − 2·clip → φRn = ' + f2(kN(stc.phiWW)) + ' kN',
            ], ['sup' + f + 'stiff']);
          }
        });

        // Panel zone
        const Pc = Fy2 * Ag2;
        const Pr = Math.abs(N2);
        const red = Pr <= 0.4 * Pc ? 1 : (1.4 - Pr / Pc);
        const twP = tw2 + (+sup.doubler || 0);
        let Rv = 0.9 * 0.6 * Fy2 * M2.d * twP * red;
        let dtxt = '';
        if (diag.on) {
          const th = Math.atan(G.dm / M2.d);
          const Ad = 2 * diag.b * diag.t;
          const add2 = 0.9 * material(diag.mat).Fy * Ad * Math.cos(th);
          Rv += add2;
          dtxt = 'Sườn chéo 2×' + diag.b + '×' + diag.t + ': + φ·Fy·Ad·cosθ = ' + f2(kN(add2)) + ' kN (θ = ' + f1(th / D2R) + '°)';
        }
        add('pz', 'Vùng panel', 'Chảy cắt vùng panel', 'kN', 'AISC J10.6 (J10-9, J10-10)', kN(Rv), kN(Vpz), nm, () => [
          'Vu = max|Ffu| ' + (inp.opt.pzSubtractShear ? '− |V cấu kiện gối|' : '') + ' = ' + f2(kN(Vpz)) + ' kN',
          'Pr = ' + f2(kN(Pr)) + ' kN;  Pc = Fy·A = ' + f2(kN(Pc)) + ' kN → hệ số = ' + f3(red),
          'φRv = 0.9·0.6·Fy·dc·tw·hệ số = 0.9·0.6·' + Fy2 + '·' + f1(M2.d) + '·' + f1(twP) + (sup.doubler > 0 ? ' (gồm bản ốp ' + sup.doubler + ' mm)' : '') + '·' + f3(red),
        ].concat(dtxt ? [dtxt] : []).concat(['φRv = ' + f2(kN(Rv)) + ' kN']), ['panel']);
      }
    });

    // ---------- Kiểm tra cấu tạo ----------
    const geo = [];
    function gchk(grp, name, val, min, max, ref, unit) {
      const ok = (min == null || val >= min - 1e-6) && (max == null || val <= max + 1e-6);
      geo.push({ grp, name, val, min, max, ref, unit: unit || 'mm', ok });
    }
    const emin = edgeMin(db, inp.opt.sheared);
    const emax = Math.min(12 * Math.min(tp, tsSup), 150);
    gchk('Bản đầu', 'Khoảng cách mép theo phương dọc bản Lev', pl.Lev, emin, emax, 'J3.4, J3.5');
    gchk('Bản đầu', 'Khoảng cách mép ngang Leh', pl.Leh, emin, emax, 'J3.4, J3.5');
    gchk('Bản đầu', 'Gage g (khoảng cách 2 dãy bu lông)', pl.g, 2.667 * db, M1.bf, 'J3.3; DG16 §2.5.3 item 7');
    const pmin = db <= 25.4 ? db + 12.7 : db + 19.05;
    if (pl.extE) gchk('Bản đầu', 'pf,o cánh ngoài', pl.pfoE, pmin, null, 'DG16 §2.5.3 item 4');
    gchk('Bản đầu', 'pf,i cánh ngoài', pl.pfiE, pmin, null, 'DG16 §2.5.3 item 4');
    if (pl.extI) gchk('Bản đầu', 'pf,o cánh trong', pl.pfoI, pmin, null, 'DG16 §2.5.3 item 4');
    gchk('Bản đầu', 'pf,i cánh trong', pl.pfiI, pmin, null, 'DG16 §2.5.3 item 4');
    if (pl.extE) gchk('Bản đầu', 'Khoảng cách hàng ngoài – hàng trong (cánh ngoài)', pl.pfoE + G.tfe + pl.pfiE, 2.667 * db, null, 'J3.3');
    if (pl.nE > 1) gchk('Bản đầu', 'Bước hàng pb (cánh ngoài)', pl.pbE, 2.667 * db, null, 'J3.3');
    if (pl.nI > 1) gchk('Bản đầu', 'Bước hàng pb (cánh trong)', pl.pbI, 2.667 * db, null, 'J3.3');
    const lastE = G.rowsE.filter((r) => !r.outer).pop(), lastI = G.rowsI.filter((r) => !r.outer).pop();
    if (lastE && lastI) gchk('Bản đầu', 'Khoảng trống giữa nhóm cánh ngoài và cánh trong', lastI.s - lastE.s, 2.667 * db, null, 'J3.3');
    gchk('Bản đầu', 'Đường kính bu lông', db, null, 38.1, 'DG4 §1.1');
    gchk('Bản đầu', 'Bề rộng bản bp ≤ bf + 25 (hiệu quả)', G.bp, null, M1.bf + IN, 'DG16 §2.5.3 item 6 (vượt → chỉ tính bf + 25.4)');
    ['E', 'I'].forEach((f) => {
      const w = f === 'E' ? inp.weld.flE : inp.weld.flI;
      if (w.type === 'fillet') gchk('Hàn', 'Hàn góc cánh ' + (f === 'E' ? 'ngoài' : 'trong') + ' ≥ min', w.w, weldMin(Math.min(M1.tf, tp)), null, 'Table J2.4');
    });
    gchk('Hàn', 'Hàn góc bụng ≥ min', inp.weld.web.w, weldMin(Math.min(M1.tw, tp)), null, 'Table J2.4');
    if (flangeSupport) ['E', 'I'].forEach((f) => {
      const st = f === 'E' ? sup.stE : sup.stI;
      if (!st || !st.on) return;
      const lab = 'Sườn gối ' + (f === 'E' ? 'cánh ngoài' : 'cánh trong');
      gchk(lab, 'bs + tw/2 ≥ bf/3', st.bs + tw2 / 2, M2.bf / 3, null, 'J10.8');
      gchk(lab, 'ts ≥ tf(kèo)/2', st.ts, (f === 'E' ? G.tfe : G.tfi) / 2, null, 'J10.8');
      gchk(lab, 'ts ≥ bs/16', st.ts, st.bs / 16, null, 'J10.8');
      gchk(lab, 'bs ≤ (bf − tw)/2', st.bs, null, (M2.bf - tw2) / 2, 'Hình học');
    });
    ['E', 'I'].forEach((f) => {
      const S = sides[f];
      if (!S || S.error || !S.stiff) return;
      const st = f === 'E' ? pl.stiffE : pl.stiffI;
      const stMat = material(st.mat);
      const hst = (f === 'E' ? pl.pfoE : pl.pfoI) + pl.Lev;
      const lab = 'Sườn bản đầu (4ES) ' + (f === 'E' ? 'ngoài' : 'trong');
      gchk(lab, 'ts ≥ tw·Fyb/Fys', st.ts, M1.tw * M1.mat.Fy / stMat.Fy, null, 'DG4 Eq. 3.15');
      gchk(lab, 'hst/ts ≤ 0.56√(E/Fys)', hst / st.ts, null, 0.56 * Math.sqrt(E / stMat.Fy), 'DG4 Eq. 3.16', '');
      gchk(lab, 'Lst ≥ hst/tan30°', st.L, hst / Math.tan(30 * D2R), null, 'DG4 §2.4');
    });

    // ---------- Tổng hợp ----------
    const list = order.map((id) => checks[id]);
    let gov = null;
    list.forEach((c) => { if (!c.info && (!gov || c.ratio > gov.ratio)) gov = c; });
    const geoFail = geo.filter((g) => !g.ok).length;
    return { G, sides, bolt, checks: list, geo, demands, gov, W, geoFail, weldF, meta: { code: 'AISC 360-10 LRFD', guides: 'DG4 (2003), DG16 (2002), DG39 (2023) App. A' } };
  }

  function condLabel(c) {
    return ({
      endplate: 'Bản đầu (như end-plate, DG16)',
      cont_unstiff: 'Cánh liên tục, không sườn',
      cont_stiff: 'Cánh liên tục, có sườn ngang',
      top_cap: 'Đỉnh cấu kiện có bản nắp',
      top_unstiff: 'Đỉnh cấu kiện, không sườn',
    })[c] || c;
  }

  root.KneeEngine = { compute, parseSection, MATERIALS, BOLT_GRADES, BOLT_DIAS, ELECTRODES, PRETENSION, condLabel, endPlateY, kennedy, boltMoments, supportYc, material };
})(typeof window !== 'undefined' ? window : globalThis);
