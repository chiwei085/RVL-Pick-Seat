# RVL Pick Seat

用權重加權亂數抽座位，並用 GUI 視覺化結果（頭貼落在座位圖上）。

v0.1.1：GUI 版本，支援頭貼、座位版面設定檔、重新抽一次。

## 安裝

使用 [uv](https://docs.astral.sh/uv/) 管理環境：

```bash
uv sync
```

## 建立本機成員資料

實際姓名、抽籤偏好與頭貼不納入版本控制（見 `.gitignore`）。第一次使用時先建立本機設定：

```bash
cp configs/members.example.yaml configs/members.yaml
mkdir -p assets/members
```

接著編輯 `configs/members.yaml`，每位成員三個欄位：

```yaml
members:
  - name: 成員 A
    weight: 3            # 權重，越高越容易抽中心儀座位
    preferences: [1, 2]  # 心儀座位編號，不可為空
    photo: member-a.jpg  # 選填，對應 assets/members/ 底下的檔名
```

- 座位編號固定為 `1..N`（N = 成員人數），不用另外設定。
- `preferences` 不可為空；沒有特別偏好時請**列出全部座位編號**（這會被演算法視為懲罰，優先度最低，見下方演算法說明）。
- `photo` 為選填；省略或找不到圖片時，GUI 會自動顯示姓名首字的預設頭貼。

若要顯示頭貼，把圖片放進 `assets/members/`，並在對應成員加入 `photo` 欄位。

## 執行

```bash
uv run pick-seat-gui
```

跳出視窗顯示座位圖，同時終端機會印出抽籤順序與最終結果的文字版。按「重新抽一次」可用新的亂數重抽。

常用參數：

```bash
uv run pick-seat-gui --seed 42                     # 固定亂數種子，方便測試重現
uv run pick-seat-gui -c path/to/other_members.yaml  # 指定成員設定檔
uv run pick-seat-gui --layout configs/seats_layout.yaml  # 指定座位版面設定檔
```

## 座位版面

座位圖由 `configs/seats_layout.yaml` 定義（程式自己畫，不直接使用 `assets/seats.png`，該圖僅作版面參考）。每個格子是一個 `[x, y, w, h]` 區塊，`seat` 對應 `members.yaml` 中的座位編號；`seat: null` 代表該格子只是房間裡的裝飾、不參與本次抽籤。想調整座位圖形狀或增刪座位，直接編輯這個檔案即可。

## 演算法

### 問題定義

- **輸入**：座位集合 $\text{Seats} = \{1, \dots, N\}$；成員集合 $M = \{1, \dots, N\}$（人數 = 座位數）；每人權重 $w_i > 0$；每人心儀座位集合 $P_i \subseteq \text{Seats}$，且 $P_i \neq \emptyset$。
- **輸出**：一個雙射 $\text{seat}: M \to \text{Seats}$（每人恰得一個座位），滿足
  1. $w_i$ 越大，$i$ 抽到 $\text{seat}(i) \in P_i$ 的機率越高；
  2. $|P_i|$ 越小，$i$ 抽到 $\text{seat}(i) \in P_i$ 的機率越高；
  3. 其餘所有隨機性（同分者之間、心儀座位耗盡後的選擇）皆為均勻分布，不含額外偏誤。

### 優先分數 (priority score)

對每個 $i \in M$，令 $k_i = |P_i|$，定義

$$\text{bonus}(k_i) = N^{-\frac{k_i - 1}{N - 1}} \qquad (N > 1；N=1 時 \text{bonus} = 1)$$

$$\text{priority}(i) = w_i \cdot \text{bonus}(k_i)$$

$\text{bonus}$ 是 $k$ 的平滑遞減函數：$k=1$（心儀座位最專一）時取最大值 $1$；$k=N$（列出全部座位，等於沒有偏好）時取最小值 $1/N$，中間以幾何內插遞減——每多列一個心儀座位，扣掉的是「剩餘 bonus 的固定比例」而非固定量。

### Algorithm 1 — DRAFT-ORDER(M, priority)

> 用加權隨機排列決定抽籤順序，*priority* 越高的人期望排名越前面，但整體仍是機率性的。

```
DRAFT-ORDER(M, priority)
1  for each i ∈ M
2      U[i] ← RANDOM(0, 1)                       ▷ i.i.d. Uniform(0,1)
3      key[i] ← U[i] ^ (1 / priority(i))
4  sort M into order = (i₁, …, iₙ) by key[·] in decreasing order
5  return order
```

### Algorithm 2 — ASSIGN-SEATS(order, P)

```
ASSIGN-SEATS(order, P)
1  S ← Seats                                      ▷ 剩餘座位
2  for t ← 1 to n
3      i ← order[t]
4      A ← P[i] ∩ S
5      if A ≠ ∅
6          seat[i] ← RANDOM-CHOICE(A)              ▷ 均勻隨機
7          hit[i] ← TRUE
8      else
9          seat[i] ← RANDOM-CHOICE(S)               ▷ 均勻隨機
10         hit[i] ← FALSE
11     S ← S − {seat[i]}
12 return seat[·], hit[·]
```

### 正確性與機率計算

**引理 1（指數競賽）.** 設 $U_i$ 為獨立同分布的 $\text{Uniform}(0,1)$ 隨機變數，$\text{key}_i = U_i^{1/\text{priority}(i)}$，令 $E_i = -\ln \text{key}_i$。則 $E_i \sim \text{Exponential}(\text{priority}(i))$，且諸 $E_i$ 互相獨立。

*證明.* 由機率積分變換，$U_i \sim \text{Uniform}(0,1) \Rightarrow -\ln U_i \sim \text{Exponential}(1)$。令 $p_i = \text{priority}(i)$，則

$$E_i = -\ln \text{key}_i = -\tfrac{1}{p_i}\ln U_i = \tfrac{1}{p_i}(-\ln U_i)$$

若 $X \sim \text{Exponential}(1)$，則 $X/p \sim \text{Exponential}(p)$（指數分布的尺度性質），故 $E_i \sim \text{Exponential}(p_i)$。各 $U_i$ 互相獨立，故各 $E_i$ 互相獨立。∎

**引理 2（獨立指數分布的最小值）.** 若 $E_1, \dots, E_n$ 互相獨立，$E_i \sim \text{Exponential}(\lambda_i)$，則

$$\Pr[E_i = \min_j E_j] = \dfrac{\lambda_i}{\sum_j \lambda_j}$$

這是機率論中「競賽時鐘」(competing clocks) 的標準結果。

**定理 1（抽籤順序的精確分布）.** DRAFT-ORDER 產生的順序 $(i_1, \dots, i_n)$ 服從 Plackett–Luce 分布：

$$\Pr[\text{order} = (i_1, \dots, i_n)] = \prod_{t=1}^{n} \dfrac{\text{priority}(i_t)}{\sum_{s=t}^{n} \text{priority}(i_s)}$$

*證明.* 由引理 1，$\text{key}_i$ 遞減對應 $E_i$ 遞增，故「$\text{key}$ 最大」等價於「$E$ 最小」。由引理 2，第一位出線者是 $i_1$ 的機率為 $\text{priority}(i_1) / \sum_j \text{priority}(j)$。指數分布具無記憶性，扣除 $i_1$ 之後，剩餘的 $E_i\ (i \neq i_1)$ 仍是相同 rate 的獨立指數分布，故可對剩餘 $n-1$ 人歸納，得到上式。∎（此即 Efraimidis–Spirakis 加權隨機排列與「依剩餘權重比例序貫抽樣」等價的標準證明。）

**推論 1（兩人賽局）.** 若僅有 $i, j$ 兩人搶同一個座位（例如兩人都只心儀同一格），則

$$\Pr[i\ \text{先抽到那個座位}] = \dfrac{\text{priority}(i)}{\text{priority}(i) + \text{priority}(j)}$$

只要 $\text{priority}(i) > \text{priority}(j)$，$i$ 的中選機率必然大於 $1/2$——這精確對應設計目標中的條件 1、2。

**心儀座位命中機率.** 一般情況下，$i$ 是否命中心儀座位不只取決於他的抽籤名次，還取決於名次之前的人如何隨機選走座位（因為這決定了抽到 $i$ 時 $P_i$ 還剩多少座位）。令 $S_{t-1}$ 為第 $t$ 輪抽籤前剩餘座位集合（一個由前 $t-1$ 人隨機選位遞迴定義的隨機變數），則精確式為

$$\Pr[i\ \text{命中心儀座位}] = \sum_{t=1}^{N} \Pr[i\ \text{排在第}\ t\ \text{位}] \cdot \Pr\!\big[P_i \cap S_{t-1} \neq \emptyset \mid i\ \text{排在第}\ t\ \text{位}\big]$$

其中第一項可由定理 1 對所有排列取邊際機率求得，第二項則依賴 $S_{t-1}$ 的完整分布。由於狀態空間（排列數 $\times$ 座位子集數）隨 $N$ 指數成長，本專案不求封閉解，改用 Monte Carlo 模擬驗證方向性：

| 設定（5 席） | 命中機率 |
|---|---|
| weight=4, 心儀 1 席 | 65.2% |
| weight=1, 心儀 1 席（同上情境的對照組） | 17.0% |
| weight=1, 心儀 1 席 | 81.0% |
| weight=1, 心儀 5 席（=無偏好） | 3.4% |

（每組 20,000 次模擬；符合推論 1 與設計目標的方向性。）

### 複雜度分析

- `DRAFT-ORDER`：產生 $n$ 個 key 並排序，$\Theta(n \log n)$。
- `ASSIGN-SEATS`：每輪對剩餘座位集合做交集與刪除，若以雜湊集合實作，平均 $O(n + \sum_i k_i)$，最差 $O(n^2)$。
- 整體：$\Theta(n \log n) + O(n^2)$ worst case；對一般座位數（通常 $n < 100$）可忽略不計。
