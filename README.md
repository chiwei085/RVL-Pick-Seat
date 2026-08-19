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

每人抽籤優先度分數：

```
priority = weight × scarcity_bonus(k)
scarcity_bonus(k) = N ** (-(k-1)/(N-1))
```

其中 `N` 為座位總數、`k` 為該成員心儀座位數量。這是一條平滑的非線性曲線：`k=1`（心儀座位最專一）時 `bonus=1`；`k=N`（列出全部座位、等於沒特別偏好）時 `bonus=1/N`，中間以幾何內插平滑遞減——每多列一個心儀座位，扣掉的是「剩餘 bonus 的固定比例」，因此完全沒偏好的人會被自然拉到最低優先度，不需要額外的特判或魔術常數。

流程：

1. 依 `priority` 做加權隨機排列（Efraimidis–Spirakis 演算法），得到抽籤順序——分數越高的人期望排越前面，但仍是機率性、非決定性的。
2. 依序輪流選位：手上心儀座位還有剩，就從中均勻隨機選一個；心儀座位已被選光或沒有心儀座位，就從剩餘座位均勻隨機選。
3. 其餘所有環節（同分者之間、心儀座位耗盡後的選擇）都是公平亂數，沒有額外偏誤。

這樣同時滿足：權重越高的人選中心儀座位機率越高；心儀座位越少（越專一）的人選中機率越高；其餘因素公平隨機。
