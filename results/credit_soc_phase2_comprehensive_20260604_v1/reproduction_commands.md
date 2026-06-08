# Phase-2 综合报告复现命令

生成时间：2026-06-04 13:27:08 CST

## 最终报告

```bash
/home/wuyangcheng/.conda/envs/myenv/bin/python scripts/build_phase2_comprehensive_report.py --strict-analysis-dir /data/WYC/class/creditNet/results/credit_soc_phase2_strict_soc_20260604_v1/analysis_final_v5 --strict-report /data/WYC/class/creditNet/docs/credit_soc_phase2_strict_soc_report_20260604_v1.md --stationarity-result-dir /data/WYC/class/creditNet/results/credit_soc_phase2_stationarity_search_20260604_v1 --stationarity-report /data/WYC/class/creditNet/docs/credit_soc_phase2_stationarity_search_report_20260604_v1.md --stationarity-verdict no_candidate --output-dir /data/WYC/class/creditNet/results/credit_soc_phase2_comprehensive_20260604_v1 --markdown /data/WYC/class/creditNet/docs/credit_soc_phase2_comprehensive_report_20260604_v1.md --docx /data/WYC/class/creditNet/docs/credit_soc_phase2_comprehensive_report_20260604_v1.docx
```

## 仅独立复算 event-definition 审计

```bash
/home/wuyangcheng/.conda/envs/myenv/bin/python scripts/build_phase2_comprehensive_report.py --strict-analysis-dir /data/WYC/class/creditNet/results/credit_soc_phase2_strict_soc_20260604_v1/analysis_final_v5 --strict-report /data/WYC/class/creditNet/docs/credit_soc_phase2_strict_soc_report_20260604_v1.md --stationarity-result-dir /data/WYC/class/creditNet/results/credit_soc_phase2_stationarity_search_20260604_v1 --stationarity-report /data/WYC/class/creditNet/docs/credit_soc_phase2_stationarity_search_report_20260604_v1.md --stationarity-verdict no_candidate --output-dir /data/WYC/class/creditNet/results/credit_soc_phase2_comprehensive_20260604_v1 --markdown /data/WYC/class/creditNet/docs/credit_soc_phase2_comprehensive_report_20260604_v1.md --docx /data/WYC/class/creditNet/docs/credit_soc_phase2_comprehensive_report_20260604_v1.docx --audit-only
```

脚本会在最终模式中强制检查 strict/stationarity worker completion、strict 修正版文件、
stationarity CSV/PNG/正式报告以及固定 `K=1` 对照；任一 gate 未通过即拒绝生成最终版。
