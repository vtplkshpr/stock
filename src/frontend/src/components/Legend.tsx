// Legend in the top-left corner of the canvas. It has no background and lets clicks through
// (pointer-events: none) so the diagram underneath stays usable; only the toggle is clickable.
import { useState } from "react";

const STORAGE_KEY = "diagram.legend.open";

function initiallyOpen(): boolean {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved !== null) return saved === "1";
  } catch {
    /* storage unavailable: fall back to the screen size */
  }
  return window.innerWidth > 720;
}

export function Legend() {
  const [open, setOpen] = useState(initiallyOpen);
  const toggle = () => {
    setOpen((value) => {
      try {
        window.localStorage.setItem(STORAGE_KEY, value ? "0" : "1");
      } catch {
        /* not remembered, still toggled */
      }
      return !value;
    });
  };

  return (
    <aside className={`legend-panel ${open ? "is-open" : ""}`} aria-label="Legend">
      <button className="legend-toggle" onClick={toggle} aria-expanded={open}>
        {open ? "▾ Legend" : "▸ Legend"}
      </button>
      {open && (
        <div className="legend-body">
          <section>
            <h4>Branches</h4>
            <p><i className="lg-dot info" /> Information grows <b>up ▲</b></p>
            <p><i className="lg-dot customers" /> <b>◀ Customers</b> on the left</p>
            <p><i className="lg-dot suppliers" /> <b>Suppliers ▶</b> on the right</p>
          </section>
          <section>
            <h4>Nodes</h4>
            <p><span className="lg-node lg-centre">SBT</span> Company at the centre</p>
            <p><span className="lg-node lg-section">Leadership <em>5/5</em></span> Branches with data / all</p>
            <p><span className="lg-node lg-section">Shareholders <em>38</em></span> Records</p>
            <p><span className="lg-node lg-section lg-empty">News <em>no data</em></span> Nothing recorded yet</p>
            <p><span className="lg-node lg-side-suppliers">Suppliers of X</span> <span className="lg-node lg-side-customers">Customers of X</span></p>
            <p><span className="lg-chip lg-chip-strong">GEG</span> Listed · <span className="lg-chip">Unlisted</span> organisation</p>
            <p><span className="lg-node lg-dashed">+ 16 more</span> Load the next partners</p>
            <p><span className="lg-node lg-dashed">↩ SBT</span> Already on the diagram – click to go there</p>
          </section>
          <section>
            <h4>Edges</h4>
            <p><i className="lg-line lg-thick" /> Thicker = larger amount (latest period)</p>
            <p><i className="lg-line lg-dash" /> Leads back to a company already shown</p>
            <p>
              <span className="lg-label"><b>42.19 bn</b><br />Mua hàng hóa <b>99.87%</b></span>
              Traded in the latest report, as worded there; % of the total in that direction. Hover for period and source file.
            </p>
          </section>
          <section>
            <h4>Dòng tiền lớn (khối ngoại, tự doanh, lệnh đặt, người nội bộ)</h4>
            <p><span className="signal lv-m2 is-compact"><span className="signal-label"><i className="signal-dot" />Cảnh báo cao</span></span> rút mạnh, đồng thuận: không mua mới, cân nhắc giảm tỷ trọng</p>
            <p><span className="signal lv-m1 is-compact"><span className="signal-label"><i className="signal-dot" />Cảnh báo</span></span> nghiêng về bán: thận trọng, chờ cải thiện</p>
            <p><span className="signal lv-p0 is-compact"><span className="signal-label"><i className="signal-dot" />Trung lập / Trái chiều</span></span> chưa rõ: theo dõi thêm</p>
            <p><span className="signal lv-p1 is-compact"><span className="signal-label"><i className="signal-dot" />Tích cực</span></span> nghiêng về mua: đưa vào danh sách theo dõi</p>
            <p><span className="signal lv-p2 is-compact"><span className="signal-label"><i className="signal-dot" />Tích cực mạnh</span></span> gom mạnh, đồng thuận: cân nhắc mua thăm dò</p>
            <p>So 20 phiên gần nhất với thói quen 60 phiên trước của chính mã; chi tiết trong nhánh "Dòng tiền lớn".</p>
          </section>
          <section>
            <h4>Units</h4>
            <p>Amounts are in VND: <b>m</b> = million (triệu) · <b>bn</b> = billion (tỷ) · <b>tn</b> = trillion (nghìn tỷ)</p>
            <p>e.g. <b>64.79 bn</b> = 64,79 tỷ đồng – the total traded in that direction in the latest report</p>
          </section>
          <section>
            <h4>Use</h4>
            <p>Click a node to open or close it · drag to move · scroll to zoom · ⤢ opens a table full size</p>
          </section>
        </div>
      )}
    </aside>
  );
}
