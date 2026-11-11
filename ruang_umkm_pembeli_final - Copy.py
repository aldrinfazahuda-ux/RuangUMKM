import json
import logging
import os
from datetime import datetime

# =====================================================================
#  RUANG UMKM - Modul Pembeli (katalog, keranjang, voucher, checkout,
#  struk, status pesanan, chat, ulasan, riwayat transaksi)
#
#  Urutan alur mengikuti flowchart "ALUR PEMBELI":
#   Katalog -> Cari & pilih produk -> Keranjang & hitung total ->
#   Checkout & pembayaran (voucher, metode bayar, struk) ->
#   Status pesanan <-> Chat -> Pesanan diterima? -> Selesaikan & ulasan ->
#   Simpan riwayat transaksi -> Cetak laporan riwayat transaksi
#
#  Tambahan pada versi ini:
#   - OOP         : class Produk, Katalog, ItemKeranjang, Keranjang,
#                   VoucherManager, Transaksi, PenyimpananData,
#                   AplikasiPembeli
#   - I/O File    : data (stok, voucher, riwayat) disimpan ke JSON,
#                   struk disimpan ke .txt, laporan diekspor ke .txt
#   - Debugging   : logging ke debug.log, verifikasi konsistensi data,
#                   penanganan error file & error tak terduga
#   - Search      : linear search (kata kunci), binary search (id produk),
#                   pencarian riwayat transaksi
#   - Sort        : insertion sort untuk menu & riwayat transaksi
# =====================================================================

# ---------- VARIABLES & DATA TYPES ----------
MAX_PEMAKAIAN = 5          # batas maksimal 1 kode voucher dipakai
MAX_PERCOBAAN = 5          # batas salah ketik kode voucher
DISKON_VOUCHER_PERSEN = 10  # diskon voucher dari total belanja (%)

# Diskon tambahan berdasarkan total belanja: (minimal belanja, persen)
# Diurutkan dari yang terbesar agar pengecekan berhenti di tier tertinggi.
TIER_DISKON = [(500000, 10), (300000, 7.5), (200000, 5)]
BATAS_DISKON_TAMBAHAN = TIER_DISKON[-1][0]

STATUS_PESANAN = ["diproses", "dikirim", "selesai"]
METODE_PEMBAYARAN = ["Tunai (COD)", "Transfer Bank", "E-Wallet", "QRIS"]
DAFTAR_BANK = ["BRI", "BNI", "Mandiri", "BCA", "BSI", "CIMB Niaga", "Permata"]
DAFTAR_EWALLET = ["ShopeePay", "DANA", "GoPay", "OVO", "LinkAja"]
NAMA_TOKO = "Warung Makan Sederhana"
FORMAT_TANGGAL = "%d-%m-%Y %H:%M"

# ---------- KONFIGURASI FILE & DEBUGGING ----------
FILE_DATA = "data_ruang_umkm.json"      # stok, voucher, riwayat
FILE_LOG = "debug.log"                  # catatan debugging
FOLDER_STRUK = "struk"                  # satu file .txt per transaksi
FILE_LAPORAN = "laporan_riwayat.txt"    # hasil ekspor laporan
DEBUG_MODE = False                      # True = log detail (level DEBUG)

logging.basicConfig(
    filename=FILE_LOG,
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(funcName)s: %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("ruang_umkm")

# Data contoh menu Warung Makan Sederhana:
# (id, nama, kategori, harga, stok)
DATA_MENU = [
    (1, "Nasi Putih (1 porsi)", "Nasi", 5000, 50),
    (2, "Telur Dadar / Ceplok", "Lauk", 5000, 30),
    (3, "Orek Tempe", "Lauk", 3000, 25),
    (4, "Ayam Goreng", "Lauk", 10000, 30),
    (5, "Ikan Tongkol Balado", "Lauk", 8000, 20),
    (6, "Sayur Daun Singkong", "Sayur", 3000, 20),
    (7, "Perkedel Kentang", "Lauk", 3000, 25),
    (8, "Tumis Usus", "Lauk", 4000, 20),
    (9, "Sayur Sop", "Sayur", 4000, 20),
    (10, "Es Teh Manis", "Minuman", 4000, 40),
]

# Daftar kode voucher valid beserta jumlah pemakaian awal
DATA_VOUCHER = {"48213976": 0, "70562184": 0, "93748215": 0}


# ---------- FUNGSI BANTU INPUT ----------
def input_angka(pesan, tipe=int, pesan_min="Nilai harus lebih dari 0. Coba lagi."):
    """Looping sampai user memasukkan angka valid (> 0)."""
    while True:
        try:
            nilai = tipe(input(pesan))
            if nilai <= 0:
                print(pesan_min)
                continue
            return nilai
        except ValueError:
            log.debug("Input angka tidak valid pada prompt: %s", pesan)
            print("Input tidak valid, masukkan angka.")


def input_pilihan(pesan, minimal, maksimal):
    """Looping sampai user memilih angka dalam rentang minimal..maksimal."""
    while True:
        try:
            nilai = int(input(pesan))
            if minimal <= nilai <= maksimal:
                return nilai
            print(f"Pilihan harus antara {minimal} dan {maksimal}.")
        except ValueError:
            log.debug("Input pilihan tidak valid pada prompt: %s", pesan)
            print("Input tidak valid, masukkan angka.")


def input_yn(pesan):
    """Looping sampai user memasukkan 'y' atau 'n'. Mengembalikan True/False."""
    while True:
        jawab = input(pesan).strip().lower()
        if jawab in ("y", "n"):
            return jawab == "y"
        print("Input tidak valid! Harap masukkan 'y' atau 'n'.")


def rp(nilai):
    return "Rp" + format(nilai, ",")


def bulatkan(nilai):
    """Pembulatan ke rupiah terdekat (0.5 dibulatkan ke atas)."""
    return int(nilai + 0.5)


def pilih_dari_daftar(judul, daftar):
    print(f"\n{judul}")
    for i, nama in enumerate(daftar, start=1):
        print(f"  {i}. {nama}")
    pilihan = input_pilihan("Pilihan: ", 1, len(daftar))
    return daftar[pilihan - 1]


def pilih_metode_pembayaran():
    """Metode utama, lalu (jika perlu) pilih bank / e-wallet yang dipakai."""
    metode = pilih_dari_daftar("Pilih metode pembayaran:", METODE_PEMBAYARAN)

    if metode == "Transfer Bank":
        bank = pilih_dari_daftar("Pilih bank:", DAFTAR_BANK)
        return f"Transfer Bank - {bank}"
    if metode == "E-Wallet":
        ewallet = pilih_dari_daftar("Pilih e-wallet:", DAFTAR_EWALLET)
        return f"E-Wallet - {ewallet}"
    return metode  # Tunai (COD) atau QRIS


# ---------- ALGORITMA SORT & SEARCH ----------
def urutkan_data(data, kunci, menurun=False):
    """
    SORT: insertion sort (stabil). Mengembalikan list baru yang sudah
    terurut berdasarkan fungsi `kunci`; data asli tidak diubah.
    """
    hasil = list(data)
    for i in range(1, len(hasil)):
        sisip = hasil[i]
        nilai = kunci(sisip)
        j = i - 1
        while j >= 0 and (kunci(hasil[j]) < nilai if menurun
                          else kunci(hasil[j]) > nilai):
            hasil[j + 1] = hasil[j]
            j -= 1
        hasil[j + 1] = sisip
    log.debug("Sort selesai: %d data, menurun=%s", len(hasil), menurun)
    return hasil


def binary_search_id(daftar, id_cari):
    """
    SEARCH: binary search produk berdasarkan id.
    Syarat: `daftar` sudah terurut menaik berdasarkan id.
    """
    kiri, kanan = 0, len(daftar) - 1
    while kiri <= kanan:
        tengah = (kiri + kanan) // 2
        if daftar[tengah].id == id_cari:
            return daftar[tengah]
        if daftar[tengah].id < id_cari:
            kiri = tengah + 1
        else:
            kanan = tengah - 1
    return None


# ---------- OOP: PRODUK & KATALOG ----------
class Produk:
    def __init__(self, id, nama, toko, kategori, harga, stok):
        self.id = id
        self.nama = nama
        self.toko = toko
        self.kategori = kategori
        self.harga = harga
        self.stok = stok

    def kurangi_stok(self, qty):
        if qty > self.stok:
            raise ValueError(
                f"Stok '{self.nama}' tidak cukup (stok {self.stok}, minta {qty})")
        self.stok -= qty
        log.debug("Stok '%s' berkurang %d -> sisa %d", self.nama, qty, self.stok)


class Katalog:
    # atribut yang boleh dipakai untuk pengurutan: label -> fungsi kunci
    KUNCI_URUT = {
        "Nama": lambda p: p.nama.lower(),
        "Harga": lambda p: p.harga,
        "Stok": lambda p: p.stok,
        "Kategori": lambda p: p.kategori.lower(),
    }

    def __init__(self, daftar_produk):
        # selalu disimpan terurut berdasarkan id agar binary search valid
        self.daftar = urutkan_data(daftar_produk, lambda p: p.id)

    @classmethod
    def dari_data_menu(cls):
        return cls([Produk(i, nama, NAMA_TOKO, kat, harga, stok)
                    for i, nama, kat, harga, stok in DATA_MENU])

    def cari_id(self, id_produk):
        """Search: binary search berdasarkan id."""
        return binary_search_id(self.daftar, id_produk)

    def cari_kata_kunci(self, kata_kunci):
        """Search: linear search berdasarkan nama, toko, atau kategori."""
        kata = kata_kunci.lower()
        return [p for p in self.daftar
                if kata in p.nama.lower()
                or kata in p.toko.lower()
                or kata in p.kategori.lower()]

    def urutkan(self, atribut, menurun=False):
        """Sort: mengembalikan salinan daftar menu yang terurut."""
        return urutkan_data(self.daftar, self.KUNCI_URUT[atribut], menurun)

    def tampilkan(self, daftar=None):
        daftar = self.daftar if daftar is None else daftar
        print(f"\n{'No':<4}{'Menu':<26}{'Harga':>9}{'Stok':>8}")
        for p in daftar:
            stok = str(p.stok) if p.stok > 0 else "Habis"
            print(f"{p.id:<4}{p.nama[:25]:<26}{p.harga:>9,}{stok:>8}")
        print()

    def verifikasi_stok(self):
        """Debugging: pastikan tidak ada stok negatif."""
        for p in self.daftar:
            if p.stok < 0:
                raise DataTidakKonsisten(f"Stok '{p.nama}' negatif: {p.stok}")


# ---------- OOP: KERANJANG ----------
class ItemKeranjang:
    def __init__(self, produk, qty):
        self.produk = produk
        self.qty = qty

    @property
    def id(self):
        return self.produk.id

    @property
    def nama(self):
        return self.produk.nama

    @property
    def toko(self):
        return self.produk.toko

    @property
    def harga(self):
        return self.produk.harga

    @property
    def total(self):
        return self.produk.harga * self.qty

    def to_dict(self):
        return {"id": self.id, "nama": self.nama, "toko": self.toko,
                "harga": self.harga, "qty": self.qty, "total": self.total}


class Keranjang:
    def __init__(self):
        self.items = []

    def kosong(self):
        return len(self.items) == 0

    def jumlah_produk(self, id_produk):
        for item in self.items:
            if item.id == id_produk:
                return item.qty
        return 0

    def tambah(self, produk, qty):
        # Produk yang sama digabung, bukan dibuat baris baru
        for item in self.items:
            if item.id == produk.id:
                item.qty += qty
                return
        self.items.append(ItemKeranjang(produk, qty))

    def ubah_jumlah(self, index, qty_baru):
        self.items[index].qty = qty_baru

    def hapus(self, index):
        return self.items.pop(index)

    @property
    def subtotal(self):
        return sum(item.total for item in self.items)

    @property
    def total_qty(self):
        return sum(item.qty for item in self.items)

    def tampilkan(self):
        """Menampilkan daftar belanja sementara (mirip struk)."""
        print("\n---------- DAFTAR BELANJA SAAT INI ----------")
        print(f"{'No':<3}{'Nama Barang':<24}{'Qty':>4}{'Harga':>9}{'Total':>10}")
        for i, item in enumerate(self.items, start=1):
            print(f"{i:<3}{item.nama[:23]:<24}{item.qty:>4}"
                  f"{item.harga:>9,}{item.total:>10,}")
        print("---------------------------------------------\n")


# ---------- OOP: VOUCHER ----------
class VoucherManager:
    def __init__(self, pemakaian=None):
        # dict kode -> jumlah pemakaian (tracking count)
        self.pemakaian = dict(DATA_VOUCHER)
        if pemakaian:
            for kode, jumlah in pemakaian.items():
                if kode in self.pemakaian:
                    self.pemakaian[kode] = int(jumlah)

    def sisa_pakai(self, kode):
        return MAX_PEMAKAIAN - self.pemakaian[kode]

    def pakai(self, kode):
        self.pemakaian[kode] += 1
        log.info("Voucher %s dipakai (total %d x)", kode, self.pemakaian[kode])

    def validasi_interaktif(self):
        """
        - Setiap kode maksimal bisa dipakai 5x (MAX_PEMAKAIAN) sebelum "hangus".
        - Kode yang salah ketik ATAU sudah hangus sama-sama dihitung sebagai
          percobaan gagal, dan user diberi kesempatan input ulang sampai
          MAX_PERCOBAAN kali.
        Mengembalikan kode voucher yang valid, atau None jika tidak memakai
        voucher. (Counter pemakaian baru bertambah setelah pesanan dikonfirmasi.)
        """
        percobaan = 0
        while percobaan < MAX_PERCOBAAN:
            kode_input = input(
                "Masukkan kode voucher (kosongkan jika tidak punya): "
            ).strip()

            if kode_input == "":
                print("Anda tidak memasukkan kode voucher. "
                      "Anda membayar dengan harga normal.")
                return None

            percobaan += 1
            sisa_percobaan = MAX_PERCOBAAN - percobaan

            if kode_input not in self.pemakaian:
                log.warning("Kode voucher tidak dikenal: %s", kode_input)
                print("Kode voucher tidak valid.", end=" ")
            elif self.pemakaian[kode_input] >= MAX_PEMAKAIAN:
                log.warning("Kode voucher hangus: %s", kode_input)
                print(f"Kode voucher '{kode_input}' sudah hangus "
                      f"(sudah dipakai {MAX_PEMAKAIAN}x).", end=" ")
            else:
                print("Kode valid! Voucher berhasil diterapkan.")
                return kode_input

            if sisa_percobaan > 0:
                print(f"Sisa kesempatan input: {sisa_percobaan}x")
            else:
                print("Kesempatan input kode voucher sudah habis. "
                      "Anda membayar dengan harga normal.")
        return None

    def tampilkan_status(self, kode_dipakai):
        print("===== STATUS VOUCHER ANDA =====")
        if kode_dipakai:
            print(f"Kode voucher digunakan   : {kode_dipakai}")
            print(f"Sisa penggunaan kode ini : {self.sisa_pakai(kode_dipakai)}x lagi")
        else:
            print("Tidak ada voucher yang digunakan pada transaksi ini.")
        print("================================\n")


# ---------- OOP: TRANSAKSI ----------
class DataTidakKonsisten(Exception):
    """Dilempar saat verifikasi data (debugging) menemukan nilai yang janggal."""


class Transaksi:
    def __init__(self, no_transaksi, tanggal, pembeli, lokasi, metode, items,
                 total_qty, voucher, subtotal, nilai_diskon, potongan_khusus,
                 nilai_diskon_khusus, total_bayar, total_hemat,
                 chat=None, ulasan=None, status="diproses"):
        self.no_transaksi = no_transaksi
        self.tanggal = tanggal
        self.pembeli = pembeli
        self.lokasi = lokasi
        self.metode = metode
        self.items = items              # list of dict (hasil to_dict item)
        self.total_qty = total_qty
        self.voucher = voucher
        self.subtotal = subtotal
        self.nilai_diskon = nilai_diskon
        self.potongan_khusus = potongan_khusus
        self.nilai_diskon_khusus = nilai_diskon_khusus
        self.total_bayar = total_bayar
        self.total_hemat = total_hemat
        self.chat = chat if chat is not None else []
        self.ulasan = ulasan if ulasan is not None else []
        self.status = status

    # --- perhitungan (OPERATORS & EXPRESSIONS) ---
    @staticmethod
    def hitung_pembayaran(subtotal, pakai_voucher):
        """
        Diskon voucher 10% dari subtotal; diskon tambahan (5% / 7,5% / 10%)
        ditentukan dari subtotal dan dihitung dari total setelah diskon voucher.
        """
        nilai_diskon = 0
        nilai_diskon_khusus = 0
        potongan_khusus = 0

        if pakai_voucher:
            nilai_diskon = bulatkan(subtotal * DISKON_VOUCHER_PERSEN / 100)
            total_bayar = subtotal - nilai_diskon

            for batas, persen in TIER_DISKON:
                if subtotal >= batas:
                    potongan_khusus = persen
                    break

            nilai_diskon_khusus = bulatkan(total_bayar * potongan_khusus / 100)
            total_bayar -= nilai_diskon_khusus
        else:
            total_bayar = subtotal

        return {
            "subtotal": subtotal,
            "nilai_diskon": nilai_diskon,
            "potongan_khusus": potongan_khusus,
            "nilai_diskon_khusus": nilai_diskon_khusus,
            "total_bayar": total_bayar,
            "total_hemat": subtotal - total_bayar,
        }

    # --- debugging ---
    def verifikasi(self):
        """Memeriksa konsistensi angka transaksi. Melempar DataTidakKonsisten."""
        if self.subtotal != sum(i["total"] for i in self.items):
            raise DataTidakKonsisten(f"{self.no_transaksi}: subtotal tidak sama "
                                     f"dengan jumlah total item")
        if self.total_qty != sum(i["qty"] for i in self.items):
            raise DataTidakKonsisten(f"{self.no_transaksi}: total_qty salah")
        harapan = self.subtotal - self.nilai_diskon - self.nilai_diskon_khusus
        if self.total_bayar != harapan:
            raise DataTidakKonsisten(
                f"{self.no_transaksi}: total_bayar {self.total_bayar} "
                f"seharusnya {harapan}")
        if self.total_bayar < 0:
            raise DataTidakKonsisten(f"{self.no_transaksi}: total_bayar negatif")
        if self.total_hemat != self.subtotal - self.total_bayar:
            raise DataTidakKonsisten(f"{self.no_transaksi}: total_hemat salah")

    # --- output struk (dikembalikan sebagai teks agar bisa dicetak & disimpan) ---
    def buat_struk(self):
        garis = "=" * 50
        b = [garis,
             "STRUK BELANJA".center(50),
             NAMA_TOKO.center(50),
             garis,
             f"No. Transaksi : {self.no_transaksi}",
             f"Tanggal       : {self.tanggal}",
             f"Nama Pembeli  : {self.pembeli}",
             f"Lokasi        : {self.lokasi}",
             f"Pembayaran    : {self.metode}",
             "-" * 50,
             f"{'Nama Barang':<24}{'Qty':>4}{'Harga':>10}{'Total':>12}",
             "-" * 50]

        for item in self.items:
            b.append(f"{item['nama'][:23]:<24}{item['qty']:>4}"
                     f"{item['harga']:>10,}{item['total']:>12,}")

        b.append("-" * 50)
        b.append(f"{'Jumlah Item':<30}{self.total_qty:>20}")
        b.append(f"{'Subtotal':<30}{rp(self.subtotal):>20}")

        if self.voucher:
            b.append(f"{'VC Diskon Voucher ' + str(DISKON_VOUCHER_PERSEN) + '%':<30}"
                     f"{'(' + format(self.nilai_diskon, ',') + ')':>20}")
            if self.potongan_khusus > 0:
                label = ('VC Diskon Tambahan '
                         + format(self.potongan_khusus, '.1f') + '%')
                b.append(f"{label:<30}"
                         f"{'(' + format(self.nilai_diskon_khusus, ',') + ')':>20}")

        b.append("-" * 50)
        b.append(f"{'TOTAL BAYAR':<30}{rp(self.total_bayar):>20}")
        b.append(f"{'ANDA HEMAT':<30}{rp(self.total_hemat):>20}")
        b.append(garis)

        # Pesan keterangan voucher
        if self.voucher and self.potongan_khusus > 0:
            b.append(f"Selamat! Voucher anda berhasil digunakan, kamu mendapatkan "
                     f"diskon tambahan {self.potongan_khusus:.1f}%")
        elif self.voucher:
            b.append(f"Dengan voucher, belanja minimal {rp(BATAS_DISKON_TAMBAHAN)} "
                     f"agar dapat diskon tambahan")
        else:
            b.append("Anda membayar dengan harga normal (tanpa diskon apapun)")
        b.append("        Terima kasih telah berbelanja!")
        return "\n".join(b)

    # --- serialisasi untuk file JSON ---
    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


# ---------- LAPORAN RIWAYAT (teks) ----------
def buat_laporan_teks(riwayat, judul="LAPORAN RIWAYAT TRANSAKSI"):
    lebar = 84
    garis = "=" * lebar
    b = [garis, judul.center(lebar), garis]
    if not riwayat:
        b.append("Tidak ada transaksi untuk ditampilkan.")
        b.append(garis)
        return "\n".join(b)

    b.append(f"{'No':<4}{'No. Transaksi':<18}{'Tanggal':<18}{'Pembeli':<12}"
             f"{'Pembayaran':<22}{'Total':>10}")
    for i, trx in enumerate(riwayat, start=1):
        b.append(f"{i:<4}{trx.no_transaksi:<18}{trx.tanggal:<18}"
                 f"{trx.pembeli[:11]:<12}{trx.metode[:21]:<22}"
                 f"{trx.total_bayar:>10,}")

    b.append("-" * lebar)
    b.append(f"{'Jumlah transaksi':<30}{len(riwayat):>20}")
    b.append(f"{'Total pendapatan':<30}"
             f"{rp(sum(t.total_bayar for t in riwayat)):>20}")
    b.append(f"{'Total hemat (diskon)':<30}"
             f"{rp(sum(t.total_hemat for t in riwayat)):>20}")
    b.append(garis)
    return "\n".join(b)


# ---------- OOP: PENYIMPANAN (I/O FILE) ----------
class PenyimpananData:
    """Semua operasi baca/tulis file dikumpulkan di sini."""

    def __init__(self, file_data=FILE_DATA):
        self.file_data = file_data

    def muat(self):
        """Membaca file JSON. Mengembalikan dict, atau None jika tidak ada/rusak."""
        if not os.path.exists(self.file_data):
            log.info("File data belum ada, memakai data awal.")
            return None
        try:
            with open(self.file_data, "r", encoding="utf-8") as f:
                data = json.load(f)
            log.info("Data dimuat dari %s", self.file_data)
            return data
        except (json.JSONDecodeError, OSError) as err:
            log.error("Gagal membaca %s: %s", self.file_data, err)
            print(f"Peringatan: file data tidak bisa dibaca ({err}). "
                  f"Program memakai data awal.")
            try:
                os.replace(self.file_data, self.file_data + ".rusak")
                log.info("File rusak dipindah ke %s.rusak", self.file_data)
            except OSError:
                pass
            return None

    def simpan(self, data):
        """Menulis JSON secara aman (tulis ke file sementara lalu ganti)."""
        sementara = self.file_data + ".tmp"
        try:
            with open(sementara, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(sementara, self.file_data)
            log.debug("Data disimpan ke %s", self.file_data)
            return True
        except OSError as err:
            log.exception("Gagal menyimpan %s", self.file_data)
            print(f"Peringatan: data gagal disimpan ({err}).")
            return False

    def simpan_teks(self, path, teks):
        """Menulis file teks (struk / laporan)."""
        try:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(teks + "\n")
            log.info("File teks disimpan: %s", path)
            return True
        except OSError as err:
            log.exception("Gagal menulis %s", path)
            print(f"Peringatan: gagal menulis file {path} ({err}).")
            return False

    def simpan_struk(self, trx):
        return self.simpan_teks(
            os.path.join(FOLDER_STRUK, f"{trx.no_transaksi}.txt"),
            trx.buat_struk())


# ---------- OOP: APLIKASI PEMBELI ----------
class AplikasiPembeli:
    def __init__(self):
        self.penyimpanan = PenyimpananData()
        self.katalog = Katalog.dari_data_menu()
        self.voucher = VoucherManager()
        self.riwayat = []          # menyimpan semua transaksi yang selesai
        self._muat_data()

    # ----- I/O FILE: muat & simpan state -----
    def _muat_data(self):
        data = self.penyimpanan.muat()
        if not data:
            return

        for kode_id, stok in data.get("stok", {}).items():
            produk = self.katalog.cari_id(int(kode_id))
            if produk is not None and int(stok) >= 0:
                produk.stok = int(stok)

        self.voucher = VoucherManager(data.get("voucher", {}))

        for d in data.get("riwayat", []):
            try:
                self.riwayat.append(Transaksi.from_dict(d))
            except (TypeError, KeyError) as err:
                log.error("Satu data riwayat dilewati (rusak): %s", err)

        print(f"Data sebelumnya dimuat: {len(self.riwayat)} transaksi "
              f"dari {self.penyimpanan.file_data}.")

    def simpan_semua(self):
        data = {
            "stok": {str(p.id): p.stok for p in self.katalog.daftar},
            "voucher": self.voucher.pemakaian,
            "riwayat": [t.to_dict() for t in self.riwayat],
        }
        return self.penyimpanan.simpan(data)

    def _buat_nomor_transaksi(self):
        awalan = f"TRX-{datetime.now():%Y%m%d}-"
        urutan = sum(1 for t in self.riwayat
                     if t.no_transaksi.startswith(awalan)) + 1
        return f"{awalan}{urutan:03d}"

    # ----- KATALOG: pilih, cari, urutkan -----
    def menu_urutkan_katalog(self):
        atribut = list(Katalog.KUNCI_URUT)
        print("\nUrutkan menu berdasarkan:")
        for i, nama in enumerate(atribut, start=1):
            print(f"  {i}. {nama}")
        print("  0. Batal")
        pilih = input_pilihan("Pilihan: ", 0, len(atribut))
        if pilih == 0:
            return
        print("  1. Naik (A-Z / termurah)   2. Turun (Z-A / termahal)")
        menurun = input_pilihan("Urutan: ", 1, 2) == 2
        terurut = self.katalog.urutkan(atribut[pilih - 1], menurun)
        self.katalog.tampilkan(terurut)

    def pilih_produk(self):
        """
        Katalog langsung ditampilkan, user tinggal memilih nomor menu.
        Mengetik kata kunci menyaring daftar menu (linear search),
        mengetik 'urut' mengurutkan daftar menu (sort).
        Mengembalikan Produk, atau None jika dibatalkan.
        """
        print(f"\n=== KATALOG MENU - {NAMA_TOKO.upper()} ===")
        self.katalog.tampilkan()

        while True:
            masukan = input(
                "Pilih nomor menu (0 = batal, 'urut' = urutkan, "
                "atau ketik kata kunci): "
            ).strip()

            if masukan == "0":
                return None

            if masukan.isdigit():
                produk = self.katalog.cari_id(int(masukan))   # binary search
                if produk:
                    return produk
                print("Nomor menu tidak ada di daftar.")
                continue

            if masukan == "":
                self.katalog.tampilkan()
                continue

            if masukan.lower() == "urut":
                self.menu_urutkan_katalog()
                continue

            hasil = self.katalog.cari_kata_kunci(masukan)      # linear search
            if hasil:
                self.katalog.tampilkan(hasil)
            else:
                print("Menu tidak ditemukan. Coba kata kunci lain.")

    # ----- KERANJANG -----
    def tambah_ke_keranjang(self, keranjang):
        produk = self.pilih_produk()
        if produk is None:
            return False

        tersedia = produk.stok - keranjang.jumlah_produk(produk.id)
        if tersedia <= 0:
            print(f"Maaf, stok '{produk.nama}' tidak tersedia "
                  f"(habis atau seluruhnya sudah ada di keranjang).")
            return False

        while True:
            jumlah = input_angka(
                f"Masukkan jumlah barang (stok tersedia {tersedia}): ", int,
                "Jumlah barang harus lebih dari 0. Coba lagi."
            )
            if jumlah <= tersedia:
                break
            print(f"Jumlah melebihi stok. Maksimal {tersedia}.")

        keranjang.tambah(produk, jumlah)
        log.debug("Keranjang: +%d x %s", jumlah, produk.nama)
        return True

    def ubah_jumlah(self, keranjang):
        nomor = input_pilihan("Nomor barang yang diubah jumlahnya (0 = batal): ",
                              0, len(keranjang.items))
        if nomor == 0:
            return
        item = keranjang.items[nomor - 1]
        while True:
            qty_baru = input_angka(
                f"Jumlah baru untuk '{item.nama}' (stok {item.produk.stok}): ", int,
                "Jumlah barang harus lebih dari 0. Coba lagi."
            )
            if qty_baru <= item.produk.stok:
                break
            print(f"Jumlah melebihi stok. Maksimal {item.produk.stok}.")
        keranjang.ubah_jumlah(nomor - 1, qty_baru)
        print("Jumlah barang berhasil diubah.")

    def hapus_barang(self, keranjang):
        nomor = input_pilihan("Nomor barang yang dihapus (0 = batal): ",
                              0, len(keranjang.items))
        if nomor == 0:
            return
        dihapus = keranjang.hapus(nomor - 1)
        print(f"'{dihapus.nama}' dihapus dari keranjang.")

    # ----- STATUS PESANAN, CHAT, ULASAN -----
    @staticmethod
    def kirim_chat(trx):
        """Kirim satu atau lebih pesan ke penjual (kosongkan untuk selesai)."""
        print("Ketik pesan untuk penjual (kosongkan jika sudah selesai):")
        while True:
            pesan = input("Pesan: ").strip()
            if pesan == "":
                break
            trx.chat.append(pesan)
            print("Pesan terkirim ke penjual.")

    def pantau_status_pesanan(self, trx):
        """
        Sesuai flowchart: Tampilkan status pesanan -> Perlu chat dengan penjual?
        -> Pesanan sudah diterima?
        - Status berjalan otomatis (diproses -> dikirim -> selesai); pembaruan
          status oleh penjual disimulasikan.
        - Chat ditawarkan sekali saat pesanan diproses.
        - "Pesanan sudah diterima?" ditanyakan sekali setelah status selesai.
          Jika belum diterima, pembeli diarahkan chat ke penjual lalu ditanya lagi.
        """
        no = trx.no_transaksi

        print(f"\n[Pesanan {no}] Status pesanan: {STATUS_PESANAN[0].upper()}")
        if input_yn("Perlu chat dengan penjual? (y/n): "):
            self.kirim_chat(trx)

        print("\n(simulasi) Penjual memperbarui status pesanan...")
        for status in STATUS_PESANAN[1:]:
            print(f"[Pesanan {no}] Status pesanan: {status.upper()}")
            log.debug("Status %s -> %s", no, status)

        while not input_yn("\nPesanan sudah diterima? (y/n): "):
            print("Jika pesanan belum sampai, silakan hubungi penjual melalui chat.")
            self.kirim_chat(trx)

    @staticmethod
    def beri_ulasan(trx):
        """Selesaikan transaksi lalu beri rating & ulasan untuk tiap toko."""
        print("\nTransaksi selesai. Silakan beri ulasan toko.")
        toko_dibeli = urutkan_data({item["toko"] for item in trx.items},
                                   lambda t: t.lower())
        for toko in toko_dibeli:
            print(f"\nToko: {toko}")
            rating = input_pilihan("Rating (1-5): ", 1, 5)
            komentar = input("Ulasan (boleh dikosongkan): ").strip()
            trx.ulasan.append({"toko": toko, "rating": rating,
                               "komentar": komentar})
        print("Terima kasih atas ulasan Anda!")

    # ----- PROSES SATU TRANSAKSI -----
    def proses_transaksi(self):
        # INPUT NAMA PEMBELI & LOKASI
        nama_pembeli = input("Masukkan nama pembeli: ").strip() or "Pelanggan"
        lokasi = input("Masukkan lokasi pembeli: ").strip() or "-"

        # LIST BELANJA (keranjang)
        keranjang = Keranjang()
        while keranjang.kosong():
            self.tambah_ke_keranjang(keranjang)

        while True:
            keranjang.tampilkan()
            print("1. Tambah barang   2. Ubah jumlah   3. Hapus barang   "
                  "4. Lanjut ke checkout")
            menu = input_pilihan("Pilih menu: ", 1, 4)

            if menu == 1:
                self.tambah_ke_keranjang(keranjang)
            elif menu == 2:
                self.ubah_jumlah(keranjang)
            elif menu == 3:
                self.hapus_barang(keranjang)
            else:
                break

            while keranjang.kosong():
                print("Keranjang kosong, silakan pilih produk.")
                self.tambah_ke_keranjang(keranjang)

        # CHECKOUT & PEMBAYARAN
        print("\n=== CHECKOUT & PEMBAYARAN ===")
        kode_dipakai = self.voucher.validasi_interaktif()
        hasil = Transaksi.hitung_pembayaran(keranjang.subtotal,
                                            kode_dipakai is not None)

        print(f"\nSubtotal    : {rp(hasil['subtotal'])}")
        print(f"Total bayar : {rp(hasil['total_bayar'])}")
        metode = pilih_metode_pembayaran()

        if not input_yn("\nKonfirmasi pesanan dan bayar sekarang? (y/n): "):
            log.info("Pesanan dibatalkan oleh pembeli '%s'", nama_pembeli)
            print("Pesanan dibatalkan. Stok dan voucher tidak berubah.\n")
            return None

        # Pesanan dikonfirmasi: kurangi stok & tambah counter voucher
        for item in keranjang.items:
            item.produk.kurangi_stok(item.qty)
        if kode_dipakai:
            self.voucher.pakai(kode_dipakai)

        trx = Transaksi(
            no_transaksi=self._buat_nomor_transaksi(),
            tanggal=datetime.now().strftime(FORMAT_TANGGAL),
            pembeli=nama_pembeli,
            lokasi=lokasi,
            metode=metode,
            items=[item.to_dict() for item in keranjang.items],
            total_qty=keranjang.total_qty,
            voucher=kode_dipakai,
            **hasil,
        )

        # DEBUGGING: verifikasi angka transaksi & stok
        try:
            trx.verifikasi()
            self.katalog.verifikasi_stok()
            log.info("Transaksi %s terverifikasi (total %s)",
                     trx.no_transaksi, trx.total_bayar)
        except DataTidakKonsisten as err:
            log.error("Data tidak konsisten: %s", err)
            print(f"Peringatan: ditemukan data tidak konsisten ({err}). "
                  f"Lihat {FILE_LOG}.")

        self.simpan_semua()   # stok & voucher langsung tersimpan

        print(f"\nPesanan {trx.no_transaksi} berhasil dikonfirmasi "
              f"dan dikirim ke toko.")
        print("\n" + trx.buat_struk() + "\n")
        if self.penyimpanan.simpan_struk(trx):
            print(f"(Struk disimpan di {FOLDER_STRUK}/{trx.no_transaksi}.txt)\n")
        self.voucher.tampilkan_status(kode_dipakai)

        # STATUS PESANAN -> CHAT -> DITERIMA -> ULASAN
        self.pantau_status_pesanan(trx)
        self.beri_ulasan(trx)
        trx.status = "selesai"

        return trx

    # ----- RIWAYAT: laporan, urutkan, cari, ekspor -----
    def menu_riwayat(self):
        daftar = self.riwayat
        judul = "LAPORAN RIWAYAT TRANSAKSI"
        print("\n" + buat_laporan_teks(daftar, judul))

        while True:
            print("\n=== MENU RIWAYAT TRANSAKSI ===")
            print("1. Tampilkan semua   2. Urutkan   3. Cari   "
                  "4. Simpan laporan ke file   0. Selesai")
            pilih = input_pilihan("Pilih menu: ", 0, 4)

            if pilih == 0:
                break
            elif pilih == 1:
                daftar, judul = self.riwayat, "LAPORAN RIWAYAT TRANSAKSI"
            elif pilih == 2:
                daftar, judul = self._urutkan_riwayat(daftar)
            elif pilih == 3:
                daftar, judul = self._cari_riwayat()
            else:
                if self.penyimpanan.simpan_teks(
                        FILE_LAPORAN, buat_laporan_teks(daftar, judul)):
                    print(f"Laporan disimpan ke {FILE_LAPORAN}")
                continue

            print("\n" + buat_laporan_teks(daftar, judul))

    def _urutkan_riwayat(self, daftar):
        print("\nUrutkan berdasarkan:")
        print("  1. Tanggal   2. Total bayar   3. Nama pembeli")
        pilih = input_pilihan("Pilihan: ", 1, 3)
        print("  1. Naik   2. Turun")
        menurun = input_pilihan("Urutan: ", 1, 2) == 2

        kunci = {
            1: lambda t: datetime.strptime(t.tanggal, FORMAT_TANGGAL),
            2: lambda t: t.total_bayar,
            3: lambda t: t.pembeli.lower(),
        }[pilih]
        label = {1: "tanggal", 2: "total bayar", 3: "nama pembeli"}[pilih]
        arah = "turun" if menurun else "naik"
        return (urutkan_data(daftar, kunci, menurun),
                f"RIWAYAT TRANSAKSI (urut {label}, {arah})")

    def _cari_riwayat(self):
        kata = input("Cari (no. transaksi / nama pembeli / metode / menu): "
                     ).strip().lower()
        hasil = [t for t in self.riwayat                       # linear search
                 if kata in t.no_transaksi.lower()
                 or kata in t.pembeli.lower()
                 or kata in t.metode.lower()
                 or any(kata in item["nama"].lower() for item in t.items)]
        log.debug("Cari riwayat '%s': %d hasil", kata, len(hasil))
        if not hasil:
            print("Transaksi tidak ditemukan.")
        return hasil, f"HASIL PENCARIAN: '{kata}'"

    # ----- LOOP UTAMA (WHILE) -----
    def jalankan(self):
        """Memungkinkan program melayani banyak transaksi dalam satu sesi."""
        log.info("Aplikasi dimulai")
        lanjut = True

        while lanjut:
            transaksi = self.proses_transaksi()

            # SIMPAN data transaksi KE riwayat transaksi (memori + file)
            if transaksi is not None:
                self.riwayat.append(transaksi)
                self.simpan_semua()

            # LANJUT ATAU TIDAK (kontrol while utama)
            lanjut = input_yn("Input transaksi lagi? (y/n): ")

        # CETAK laporan riwayat transaksi
        self.menu_riwayat()
        print("Terima kasih, program selesai.")
        log.info("Aplikasi selesai normal")


# ---------- TITIK MASUK PROGRAM ----------
def main():
    app = None
    try:
        app = AplikasiPembeli()
        app.jalankan()
    except KeyboardInterrupt:
        print("\nProgram dihentikan pengguna.")
        log.warning("Program dihentikan dengan Ctrl+C")
    except Exception:
        log.exception("Error tak terduga")
        print(f"\nTerjadi kesalahan tak terduga. Detail ada di {FILE_LOG}.")
    finally:
        if app is not None:
            app.simpan_semua()   # pastikan data terakhir tidak hilang


if __name__ == "__main__":
    main()
