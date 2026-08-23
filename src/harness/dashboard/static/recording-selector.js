/* Keeps the paired-recording picker beside the side-by-side comparison. */

const select = document.querySelector("#pair-selector");
const count = document.querySelector("#pair-selector-count");
const currentId = decodeURIComponent(location.pathname.split("/").pop());

async function loadPairs() {
  try {
    const response = await fetch("/api/pairs");
    if (!response.ok) throw new Error("Unable to load recordings");
    const pairs = await response.json();
    select.replaceChildren();
    if (!pairs.length) {
      const option = new Option("No paired recordings available", "");
      option.disabled = true;
      select.append(option);
      select.disabled = true;
      return;
    }
    for (const pair of pairs) {
      const label = `${pair.task || "Untitled experiment"} · ${String(pair.comparison_status || "unreviewed").replaceAll("_", " ")}`;
      const option = new Option(label, pair.pair_id);
      option.selected = pair.pair_id === currentId;
      select.append(option);
    }
    count.textContent = `${pairs.length} paired recording${pairs.length === 1 ? "" : "s"}`;
    select.onchange = () => {
      if (select.value && select.value !== currentId) {
        location.assign(`/pairs/${encodeURIComponent(select.value)}`);
      }
    };
  } catch {
    select.replaceChildren(new Option("Recording list unavailable", ""));
    select.disabled = true;
  }
}

loadPairs();
