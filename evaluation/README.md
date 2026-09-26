# Retrieval evaluation

## Ground truth 標註原則

`questions.json` 的 `ground_truth_pages` 表示：

> 哪些頁面包含足以回答這題的 evidence？

不限於答案第一次出現或主要介紹答案的頁面。同一問題的有效證據可能出現在
Abstract、Introduction、Method 或 Conclusion；必須人工確認頁面內容，不能
僅依 section title 判定。頁碼使用系統回傳的 PDF `page_number`。

### Q1 的修訂

`liu2025_q1`：What is the main problem that ProtoGCN aims to address?

Ground truth 由 `[1, 2]` 改為 `[1, 2, 8]`，依使用者人工判讀：

- Page 1：Abstract / Introduction，說明研究問題。
- Page 2：Proposed approach，直接支持要解決的問題。
- Page 8：Conclusion，再次說明研究問題，亦為有效證據。

這是目前確認的有效頁面，後續若找到其他足以回答問題的頁面，可再補標。
Q2–Q5 尚未在這次修訂中重新審核。

## Hit@K 的解讀

對每題，若排名前 K 個 retrieved chunks 中，至少一個 chunk 的 `page_number`
出現在 `ground_truth_pages`，則 page-level Hit@K = 1，否則為 0。
整份資料集的 Hit@K 是各題命中值的平均。

K 應以原始 chunk 排名計算，不要先將頁碼去重後再截取 Top-K。
Retrieved chunks 不必全部相關；命中足夠的 evidence 就可能讓 retrieval 成功。
但 page-level hit 是近似指標：同頁的某個 chunk 不一定包含標註時認定的證據。
因此仍需另外檢查回答內容、groundedness 和引用是否正確；Hit@K 本身不代表
回答一定正確，也不表示多部分問題的證據已全部涵蓋。

## Q1 人工檢查紀錄

以下由使用者提供，並非本次執行腳本或重新驗證模型的結果：

- Retrieved pages：Page 2、Page 4、Page 8。
- Hit@1、Hit@3、Hit@5：皆通過（使用者回報）。
- Answer correctness：通過。
- Groundedness：通過。
- Citation correctness：通過。

目前未保存完整的 ranked chunks、模型回答或引用原文，因此這份紀錄不能
當作可重現的自動評估結果。自動 retrieval 結果另存於 `results.json`，包含 ranked pages 與 Hit@K；
它不包含生成回答或人工 generation 評分。

## Generation evaluation（人工評分）

在專案根目錄執行：

```sh
source backend/venv/bin/activate
python evaluation/evaluate_generation.py
```

脚本讀取 `questions.json`，逐題呼叫 `app.ask_service.answer_question`。
`POST /papers/ask` 也使用同一函式：embedding → Top-5 search → `generate_answer`。
評估僅多保存當次實際傳給模型的 chunks；沒有另一套 RAG，也不重用舊 retrieval
結果。執行會呼叫 OpenAI embeddings 和回答模型，需可用的 `backend/.env` 與資料庫。

輸出為 `evaluation/generation_results.json`，包含 Question、Answer、Retrieved pages、
Cited pages、來源 chunk 內容及空白 `review` 欄位。每題完成即存檔；失敗會記錄錯誤，
繼續下一題。重跑時用 `--resume` 保留已完成的答案與人工評分、重試失敗或未完成題目。
若要全新實驗，使用 `--output evaluation/generation_results_run2.json`。

請人工將每題 `review` 的三項指標填為 `true`（通過）、`false`（未通過）；
尚未檢查維持 `null`，並可在 `notes` 記錄原因：

- `answer_correctness`：依原始論文判斷是否正確回答問題，包括題目的各個部分。
- `groundedness`：回答中的主張是否有當次 retrieved chunks 的證據支持。
- `citation_correctness`：引用頁面是否真的支持相應主張；不能只看頁碼是否被檢索到。

`cited_pages` 支援 `[Page 3]`、`[Page 3; Page 4]`、`[Pages 2, 7, 8]`
等格式，頁碼去重且保留首次出現順序。頁碼範圍等有歧義的格式仍保留在
`unparsed_citations` 供人工核對；沒有解析出的引用不代表回答沒有引用。

若只修改 citation parser，可重算既有答案的衍生欄位，不重新執行 retrieval、
embedding 或回答模型：

```sh
python evaluation/evaluate_generation.py --reparse-citations
```

評分後執行（不會呼叫 OpenAI）：

```sh
python evaluation/evaluate_generation.py --summary
```

只對已評分題目計算通過率，同時顯示已評分數／總題數。未評分及執行失敗不會被
當成通過。全部 15 題成功且評分完成後，才可報告以 15 題為分母的最終分數。
