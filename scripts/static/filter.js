// 實驗表依狀態篩選。沒有 JS 時按鈕保持隱藏、表格顯示全部。
(function () {
  var bar = document.querySelector(".filters");
  if (!bar) return;
  bar.hidden = false;
  var rows = document.querySelectorAll("tr[data-status]");
  bar.addEventListener("click", function (e) {
    var btn = e.target.closest("button");
    if (!btn) return;
    var want = btn.dataset.filter;
    bar.querySelectorAll("button").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b === btn));
    });
    rows.forEach(function (r) {
      r.hidden = want !== "all" && r.dataset.status !== want;
    });
  });
})();
