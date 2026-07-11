(() => {
  const form = document.querySelector(".backtest-main-form");
  const panel = document.querySelector("[data-backtest-job-status]");
  const button = document.querySelector("[data-backtest-submit]");
  const title = document.querySelector("[data-backtest-job-title]");
  const detail = document.querySelector("[data-backtest-job-detail]");
  if (!form || !panel || !button || !title || !detail || !window.fetch) {
    return;
  }

  const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  const readJson = async (response) => {
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    return payload;
  };

  const showFailure = (message) => {
    panel.dataset.state = "failed";
    title.textContent = "回测任务失败";
    detail.textContent = message;
    button.disabled = false;
    button.textContent = "重新运行回测";
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    panel.hidden = false;
    panel.dataset.state = "running";
    title.textContent = "正在提交回测任务";
    detail.textContent = "后台任务启动后会持续显示已用时间。";
    button.disabled = true;
    button.textContent = "回测运行中";

    try {
      const body = new URLSearchParams(new FormData(form));
      let job = await fetch("/api/backtest/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
        body,
      }).then(readJson);

      while (job.status === "queued" || job.status === "running") {
        const elapsed = Number(job.elapsed_seconds || 0).toFixed(1);
        title.textContent = job.status === "queued" ? "回测任务排队中" : "正在计算历史回测";
        detail.textContent = `已运行 ${elapsed} 秒，完成后将自动展示报告。`;
        await wait(800);
        job = await fetch(`/api/backtest/jobs/${encodeURIComponent(job.job_id)}`, {
          headers: { Accept: "application/json" },
        }).then(readJson);
      }

      if (job.status === "failed" && !job.result_available) {
        throw new Error(job.error || "回测任务执行异常。");
      }
      if (!job.redirect_url) {
        throw new Error(job.error || "回测任务未返回结果地址。");
      }
      title.textContent = job.status === "completed" ? "回测完成，正在加载报告" : "回测未完成，正在显示诊断";
      detail.textContent = job.error || `总耗时 ${Number(job.elapsed_seconds || 0).toFixed(1)} 秒。`;
      window.location.assign(job.redirect_url);
    } catch (error) {
      showFailure(error instanceof Error ? error.message : String(error));
    }
  });
})();
