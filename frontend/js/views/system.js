// The system status: a chip in the header, and a banner while the models load or the server is unreachable.
import { byId, setVisible } from "../dom.js";
import { t } from "../i18n.js";

export function mountSystemView(store) {
  const chip = byId("system-chip");
  const banner = byId("system-banner");
  store.subscribe(({ status }) => {
    const chipShown = status !== "checking";
    setVisible(chip, chipShown);
    if (chipShown) {
      chip.textContent = t(`system.chip.${status}`);
      chip.className = `chip chip-${status}`;
    }
    const bannerShown = status === "loading" || status === "unreachable";
    setVisible(banner, bannerShown);
    if (bannerShown) banner.textContent = t(`system.banner.${status}`);
  }, ["status"]);
}
