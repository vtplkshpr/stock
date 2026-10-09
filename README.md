# Stock

Module tra cứu thông tin doanh nghiệp niêm yết. Ứng dụng terminal đọc dữ liệu từ MySQL/MariaDB và tải danh sách theo từng trang.

## Chức năng

- Tìm doanh nghiệp theo mã cổ phiếu hoặc tên.
- Duyệt danh sách công ty đã có trong database.
- Xem thông tin công ty, giá cổ phiếu, cổ đông, nhà cung cấp, khách hàng, báo cáo tài chính và tin tức.
- Chuyển trang bằng truy vấn `LIMIT/OFFSET`; không tải toàn bộ danh sách vào bộ nhớ.
- Với tin tức, nội dung text đầy đủ chỉ được truy vấn sau khi chọn một tin.

Database hiện lưu các nhóm dữ liệu sau:

- `companies`: thông tin cơ bản và mã niêm yết.
- `stock_prices`: giá và khối lượng giao dịch theo ngày.
- `stock_holders`: cổ đông và tỷ lệ nắm giữ theo ngày chốt.
- `finance_reports`: chỉ số tài chính, chỉ số bổ sung và đường dẫn tài liệu.
- `tiers`, `company_tiers`: phân loại doanh nghiệp.
- `supply_chain_relations`: quan hệ nhà cung cấp và khách hàng.
- `company_news`: tin text và metadata/path cho media.

Script hiện tạo schema và CLI để đọc dữ liệu; chưa có tác vụ thu thập hoặc nhập dữ liệu thị trường. Các màn hình sẽ rỗng cho tới khi database được nạp dữ liệu.

## Cài đặt nhanh

Yêu cầu Ubuntu/Debian, Python 3, quyền `sudo` và kết nối mạng trong lần cài đầu. Từ thư mục module:

```bash
cd ~/stock/stock
./scripts/setup_database.sh
```

Script dùng MariaDB/MySQL đã cài nếu có; nếu chưa có, script cài MySQL Server. Script khởi động dịch vụ, tạo database và user ứng dụng, cài `mysql-connector-python`, rồi tạo các bảng. Thông tin kết nối được lưu trong `.env` tại thư mục này với quyền `600`. File `.env` đã được Git ignore.

## Chạy CLI

Từ thư mục module, kích hoạt virtualenv mà setup đã tìm thấy hoặc tạo:

```bash
source ../venv/bin/activate
python scripts/stock_cli.py
```

Nếu virtualenv được tạo trong project, dùng `source .venv/bin/activate` hoặc `source venv/bin/activate` tương ứng.

Menu chính:

1. **Tìm kiếm doanh nghiệp** theo mã hoặc tên.
2. **Xem danh sách doanh nghiệp** và duyệt từng trang.

Trong danh sách, nhập `n`/`p` để chuyển tới/trở về một trang, chọn số thứ tự để mở công ty, hoặc `b` để quay lại. Trong hồ sơ công ty, chọn giá cổ phiếu, cổ đông, nhà cung cấp (upstream), khách hàng (downstream), báo cáo tài chính hoặc tin tức.

Có thể mở thẳng giao diện tìm kiếm:

```bash
python scripts/stock_cli.py --query HPG --page-size 20
```

`--page-size` nhận giá trị từ 1 đến 100, mặc định là 10. Ở menu chính, nhập `q` để thoát.

CLI đọc `.env` trong thư mục module. Có thể ghi đè cấu hình bằng `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD` và `MYSQL_DATABASE`.

## Cấu trúc chính

```text
stock/
├── main.py
├── module_info_draft.py
├── scripts/
│   ├── init_database.py
│   ├── setup_database.sh
│   └── stock_cli.py
├── README.md
└── SETUP.md
```

Lệnh chạy giao diện tra cứu là `scripts/stock_cli.py`. `scripts/init_database.py` là script mức thấp, nhận kết nối qua tham số hoặc biến `MYSQL_*` (không tự đọc `.env`); quy trình khởi tạo thông thường nên chạy qua `scripts/setup_database.sh`.

## Tài liệu

- [SETUP.md](SETUP.md): hướng dẫn cài đặt, cấu hình và xử lý lỗi.