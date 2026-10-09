# Cài đặt và sử dụng

Hướng dẫn này dành cho stock module hiện tại. Module dùng MySQL/MariaDB để lưu dữ liệu và cung cấp CLI terminal để tra cứu doanh nghiệp.

## Yêu cầu

- Ubuntu hoặc Debian.
- Python 3.10 trở lên và `venv`.
- Quyền `sudo` để cài/khởi động database server và tạo database user.
- Kết nối mạng nếu cần cài MySQL Server hoặc Python connector.

Script hỗ trợ MariaDB hoặc MySQL đã cài; nếu không tìm thấy server thì cài `mysql-server`. Trên máy hiện tại, database server đang dùng là MariaDB.

## Cài database

Từ thư mục module:

```bash
cd ~/stock/stock
./scripts/setup_database.sh
```

Script sẽ:

1. Kiểm tra/cài và khởi động MariaDB hoặc MySQL.
2. Tạo database (mặc định `stock_market`) và user ứng dụng (mặc định `stock_app`).
3. Sinh mật khẩu ngẫu nhiên nếu `MYSQL_PASSWORD` chưa được cung cấp.
4. Dùng virtualenv hiện có hoặc tạo một virtualenv cho project, rồi cài `mysql-connector-python`.
5. Ghi cấu hình kết nối vào `.env` tại thư mục gốc module và khởi tạo các bảng.

Setup cần quyền quản trị database qua socket, nên có thể yêu cầu mật khẩu `sudo`. Script không cần đăng nhập bằng mật khẩu MySQL của `root`.

### Cấu hình kết nối

`.env` chứa các biến sau:

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=stock_app
MYSQL_PASSWORD=<generated-password>
MYSQL_DATABASE=stock_market
```

Đây là ví dụ về tên biến, không phải credentials dùng chung. Setup tạo file với quyền `600`; `.gitignore` loại `.env` khỏi Git. Không commit hoặc chia sẻ file này. Các biến môi trường `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` sẽ ghi đè giá trị trong `.env` khi chạy CLI.

## Schema database

`scripts/init_database.py` tạo các bảng InnoDB dùng `utf8mb4`:

| Bảng | Nội dung |
| --- | --- |
| `companies` | Mã cổ phiếu, tên, sàn, ngành và thông tin cơ bản |
| `stock_prices` | Giá mở/cao/thấp/đóng cửa và khối lượng theo ngày |
| `stock_holders` | Cổ đông, lượng cổ phần và tỷ lệ sở hữu theo ngày chốt |
| `finance_reports` | Các chỉ số tài chính, JSON chỉ số bổ sung và đường dẫn tài liệu |
| `tiers` | Danh mục phân loại doanh nghiệp |
| `company_tiers` | Liên kết doanh nghiệp với tier |
| `supply_chain_relations` | Nhà cung cấp, khách hàng, danh mục sản phẩm và tỷ trọng |
| `company_news` | Tin dạng text và thông tin URL/đường dẫn media |

Các khóa ngoại liên kết dữ liệu liên quan về `companies`; xóa một công ty sẽ cascade tới dữ liệu con. Script khởi tạo dùng `CREATE TABLE IF NOT EXISTS`, nên có thể chạy lại để tạo bảng còn thiếu mà không xóa dữ liệu hiện có.

## Chạy CLI

Setup ưu tiên virtualenv trong `.venv/` hoặc `venv/` của module, sau đó mới tới `../venv/`. Kích hoạt đúng môi trường nếu muốn chạy lệnh `python` ngắn:

```bash
cd ~/stock/stock
source ../venv/bin/activate
python scripts/stock_cli.py
```

Nếu setup đã dùng virtualenv khác, thay đường dẫn `source` tương ứng, hoặc gọi Python trực tiếp, ví dụ:

```bash
../venv/bin/python scripts/stock_cli.py
```

CLI mở menu chính:

1. **Tìm kiếm doanh nghiệp** theo mã hoặc tên.
2. **Xem danh sách doanh nghiệp** theo từng trang.

Trong danh sách, nhập số thứ tự để chọn công ty, `n`/`p` để chuyển trang và `b` để quay lại. Hồ sơ công ty có các mục giá cổ phiếu, cổ đông, nhà cung cấp upstream, khách hàng downstream, báo cáo tài chính và tin tức. Các danh sách được truy vấn theo trang; nội dung đầy đủ của tin chỉ được tải khi chọn tin đó.

Tìm kiếm nhanh mà không qua menu:

```bash
python scripts/stock_cli.py --query HPG --page-size 20
```

Page size mặc định là 10, nhận từ 1 đến 100. `--help` hiển thị các tham số CLI.

## Nạp dữ liệu

Hiện tại `setup_database.sh` và `init_database.py` chỉ cài database và tạo schema; CLI chỉ tra cứu dữ liệu đã có. Project chưa có collector/importer tự động cho danh sách doanh nghiệp, giá, cổ đông, báo cáo hoặc tin tức. Database mới khởi tạo vì vậy có thể chưa trả về kết quả cho tới khi được nạp dữ liệu bằng quy trình nhập riêng.

Các mức giá và chỉ số tài chính là `DECIMAL`; nếu tài liệu báo cáo không tách được thành số liệu, lưu đường dẫn tài liệu trong `finance_reports.document_storage_path`. Tin có thể lưu nội dung text hoặc media URL/đường dẫn trong `company_news`.

## Xử lý lỗi

### Không kết nối được database

Kiểm tra dịch vụ:

```bash
sudo systemctl status mariadb
```

Nếu đang dùng MySQL thay vì MariaDB:

```bash
sudo systemctl status mysql
```

Xác nhận `.env` tồn tại tại thư mục module và có quyền `600`. Không in hoặc gửi giá trị `MYSQL_PASSWORD` khi chia sẻ log.

### Access denied cho tài khoản database

Không đổi cấu hình sang `root` để chạy CLI. Chạy lại `./scripts/setup_database.sh` trong terminal để tạo/cập nhật user `stock_app` qua socket quản trị và ghi credentials mới vào `.env`.

### Thiếu `mysql.connector`

Chạy CLI bằng đúng virtualenv đã được setup dùng, hoặc kích hoạt virtualenv rồi cài connector:

```bash
python -m pip install mysql-connector-python
```

### Không tìm thấy doanh nghiệp

Kiểm tra database đã được nạp dữ liệu chưa. Setup chỉ tạo bảng, không tự tải dữ liệu doanh nghiệp hoặc giá thị trường.