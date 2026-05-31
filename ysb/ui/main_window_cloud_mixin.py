from ysb.ui.main_window_support import *


class MainWindowCloudMixin:

    def cloud_dir(self):
        path = get_cache_dir() / "cloud"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cloud_config_path(self):
        return self.cloud_dir() / "cloud_config.json"

    def cloud_token_path(self):
        return self.cloud_dir() / "google_drive_token.json"

    def cloud_client_secret_path(self):
        return self.cloud_dir() / "google_oauth_client_secret.json"

    def load_cloud_config(self):
        try:
            p = self.cloud_config_path()
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def save_cloud_config(self, data):
        data = dict(data or {})
        self.cloud_dir().mkdir(parents=True, exist_ok=True)
        with open(self.cloud_config_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def cloud_is_registered(self):
        return self.cloud_token_path().exists()

    def cloud_status_text(self):
        cfg = self.load_cloud_config()
        if self.cloud_is_registered():
            email = str(cfg.get("account_email") or "").strip()
            when = str(cfg.get("registered_at") or "").strip()
            bits = [self.tr_ui("등록됨")]
            if email:
                bits.append(email)
            if when:
                bits.append(when)
            return " / ".join(bits)
        return self.tr_ui("미등록")

    def google_cloud_dependency_error_text(self, missing):
        missing = list(missing or [])
        package_hint = "google-auth google-auth-oauthlib google-api-python-client"
        return (
            self.tr_ui("Google Drive OAuth 연동에 필요한 파이썬 라이브러리가 없습니다.")
            + "\n\n"
            + self.tr_ui("누락 모듈:")
            + "\n"
            + "\n".join(f"- {m}" for m in missing)
            + "\n\n"
            + self.tr_ui("개발/테스트 환경에서는 아래 명령으로 설치할 수 있습니다.")
            + f"\n\npip install {package_hint}"
            + "\n\n"
            + self.tr_ui("EXE 배포판에서는 빌드 시 위 라이브러리를 함께 포함해야 합니다.")
        )

    def import_google_oauth_modules(self):
        missing = []
        InstalledAppFlow = None
        Credentials = None
        Request = None
        build = None
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow as _InstalledAppFlow
            InstalledAppFlow = _InstalledAppFlow
        except Exception as e:
            missing.append(f"google_auth_oauthlib.flow ({e})")
        try:
            from google.oauth2.credentials import Credentials as _Credentials
            Credentials = _Credentials
        except Exception as e:
            missing.append(f"google.oauth2.credentials ({e})")
        try:
            from google.auth.transport.requests import Request as _Request
            Request = _Request
        except Exception as e:
            missing.append(f"google.auth.transport.requests ({e})")
        try:
            from googleapiclient.discovery import build as _build
            build = _build
        except Exception as e:
            missing.append(f"googleapiclient.discovery ({e})")
        if missing:
            raise ImportError(self.google_cloud_dependency_error_text(missing))
        return InstalledAppFlow, Credentials, Request, build

    def cloud_oauth_candidate_paths(self):
        """OAuth 클라이언트 JSON 후보를 자동 탐색한다.
        배포판에서는 EXE 옆 cloud_oauth_client.json을 두면 사용자는 로그인만 누르면 된다.
        """
        names = [
            "cloud_oauth_client.json",
            "google_oauth_client_secret.json",
            "client_secret.json",
            "ysb_google_oauth_client.json",
        ]
        candidates = []
        try:
            candidates.append(self.cloud_client_secret_path())
        except Exception:
            pass

        roots = []
        try:
            roots.append(Path.cwd())
        except Exception:
            pass
        try:
            roots.append(APP_ROOT)
        except Exception:
            pass
        try:
            if getattr(sys, "frozen", False):
                roots.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass

        for root in roots:
            for name in names:
                candidates.append(Path(root) / name)
            try:
                candidates.extend(sorted(Path(root).glob("client_secret*.json")))
            except Exception:
                pass

        for name in names:
            try:
                candidates.append(Path(resource_path(name)))
            except Exception:
                pass

        out = []
        seen = set()
        for p in candidates:
            try:
                key = str(Path(p).resolve()).lower()
            except Exception:
                key = str(p).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(Path(p))
        return out

    def is_valid_google_oauth_client_secret(self, path):
        try:
            p = Path(path)
            if not p.exists() or not p.is_file():
                return False
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return False
            obj = data.get("installed") or data.get("web") or {}
            return bool(obj.get("client_id") and obj.get("auth_uri") and obj.get("token_uri"))
        except Exception:
            return False

    def find_default_cloud_client_secret(self):
        for p in self.cloud_oauth_candidate_paths():
            if self.is_valid_google_oauth_client_secret(p):
                return str(p)
        return ""

    def copy_cloud_client_secret(self, src_path):
        src_path = Path(str(src_path or ""))
        if not src_path.exists():
            raise FileNotFoundError(str(src_path))
        dst = self.cloud_client_secret_path()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(src_path), str(dst))
        return dst

    def select_cloud_client_secret_json(self, parent=None):
        path, _ = QFileDialog.getOpenFileName(
            parent or self,
            self.tr_ui("Google OAuth 클라이언트 JSON 선택"),
            "",
            self.tr_ui("JSON 파일 (*.json);;모든 파일 (*)"),
        )
        return path or ""

    def run_google_drive_oauth(self, client_secret_path, parent=None):
        """Google Drive OAuth 로그인 창을 열고 토큰을 로컬 캐시에 저장한다.

        기존 InstalledAppFlow.run_local_server()는 브라우저 창을 닫거나 로그인을 취소했을 때
        UI 스레드를 오래 붙잡을 수 있어, 취소 가능한 로컬 콜백 서버를 직접 띄운다.
        - 사용자가 Google 화면에서 취소/거부하면 CloudOAuthCancelled로 정상 취소 처리
        - 진행 창의 취소/X 버튼을 누르면 CloudOAuthCancelled로 정상 취소 처리
        - 제한 시간 동안 콜백이 없으면 CloudOAuthCancelled로 정상 취소 처리
        """
        InstalledAppFlow, Credentials, Request, build = self.import_google_oauth_modules()

        client_secret_path = Path(str(client_secret_path or ""))
        if not client_secret_path.exists():
            raise FileNotFoundError(str(client_secret_path))

        scopes = ["https://www.googleapis.com/auth/drive.file"]
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), scopes=scopes)

        result = {"code": "", "state": "", "error": "", "error_description": ""}
        callback_received = threading.Event()
        cancel_requested = threading.Event()

        class OAuthCallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                # 콘솔 노이즈 방지
                return

            def do_GET(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query or "")
                result["code"] = str((query.get("code") or [""])[0] or "")
                result["state"] = str((query.get("state") or [""])[0] or "")
                result["error"] = str((query.get("error") or [""])[0] or "")
                result["error_description"] = str((query.get("error_description") or [""])[0] or "")

                if result["error"]:
                    title = "YSB Tool cloud registration was cancelled."
                    body = "You can close this browser window and return to YSB Tool."
                else:
                    title = "YSB Tool cloud registration is complete."
                    body = "You can close this browser window and return to YSB Tool."

                html = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>YSB Tool</title></head>
<body style=\"font-family:Arial,sans-serif;background:#111;color:#eee;padding:32px;\">
<h2>{title}</h2>
<p>{body}</p>
</body></html>""".encode("utf-8")
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html)))
                    self.end_headers()
                    self.wfile.write(html)
                finally:
                    callback_received.set()

        # 포트 0으로 OS가 빈 포트를 배정하게 한다.
        server = HTTPServer(("localhost", 0), OAuthCallbackHandler)
        server.timeout = 0.25
        host, port = server.server_address
        redirect_uri = f"http://localhost:{port}/"
        flow.redirect_uri = redirect_uri

        # CSRF 방지용 state는 google-auth-oauthlib가 반환한 값을 검증한다.
        auth_url, expected_state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )

        def serve_until_done():
            try:
                while not callback_received.is_set() and not cancel_requested.is_set():
                    server.handle_request()
            finally:
                try:
                    server.server_close()
                except Exception:
                    pass

        thread = threading.Thread(target=serve_until_done, daemon=True)
        thread.start()

        progress = QProgressDialog(parent or self)
        progress.setWindowTitle(self.tr_ui("클라우드 등록"))
        progress.setLabelText(self.tr_ui("브라우저에서 Google 로그인을 완료해 주세요.\n로그인을 취소했거나 창을 닫았다면 아래 취소를 누르세요."))
        progress.setCancelButtonText(self.tr_ui("취소"))
        progress.setRange(0, 0)
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        try:
            apply_progress_dialog_theme(progress, self.is_light_theme())
        except Exception:
            pass
        progress.show()

        try:
            webbrowser.open(auth_url)
        except Exception as e:
            cancel_requested.set()
            try:
                progress.close()
            except Exception:
                pass
            raise RuntimeError(self.tr_ui("브라우저를 열 수 없습니다." ) + f"\n{e}")

        timeout_seconds = 300
        deadline = time.time() + timeout_seconds
        try:
            while not callback_received.is_set():
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
                if progress.wasCanceled():
                    cancel_requested.set()
                    raise CloudOAuthCancelled(self.tr_ui("클라우드 등록이 취소되었습니다."))
                if time.time() > deadline:
                    cancel_requested.set()
                    raise CloudOAuthCancelled(self.tr_ui("제한 시간 안에 Google 로그인이 완료되지 않아 클라우드 등록을 취소했습니다."))
                time.sleep(0.05)
        finally:
            cancel_requested.set()
            try:
                progress.close()
            except Exception:
                pass
            try:
                thread.join(timeout=1.0)
            except Exception:
                pass

        if result.get("error"):
            error = str(result.get("error") or "")
            desc = str(result.get("error_description") or "")
            if error in {"access_denied", "user_cancelled", "consent_required"}:
                raise CloudOAuthCancelled(self.tr_ui("Google 로그인이 취소되었습니다."))
            raise RuntimeError(f"OAuth error: {error}\n{desc}".strip())

        if expected_state and result.get("state") and result.get("state") != expected_state:
            raise RuntimeError(self.tr_ui("OAuth 응답 검증에 실패했습니다. 다시 시도해 주세요."))

        code = str(result.get("code") or "")
        if not code:
            raise CloudOAuthCancelled(self.tr_ui("Google 로그인 응답을 받지 못해 클라우드 등록을 취소했습니다."))

        # code를 토큰으로 교환한다. 여기서 실패하면 실제 등록 실패로 처리한다.
        flow.fetch_token(code=code)
        creds = flow.credentials
        if not creds:
            raise RuntimeError(self.tr_ui("Google OAuth 토큰을 가져오지 못했습니다."))

        # 연결 검증 겸 계정 정보를 최대한 가져온다.
        account_email = ""
        try:
            drive = build("drive", "v3", credentials=creds)
            about = drive.about().get(fields="user").execute()
            user = about.get("user") if isinstance(about, dict) else {}
            account_email = str((user or {}).get("emailAddress") or "")
        except Exception:
            account_email = ""

        self.cloud_token_path().parent.mkdir(parents=True, exist_ok=True)
        with open(self.cloud_token_path(), "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        # client_secret도 캐시 폴더에 복사해 두면 원본 JSON 위치가 바뀌어도 토큰 갱신에 쓸 수 있다.
        cached_secret = self.copy_cloud_client_secret(client_secret_path)

        cfg = self.load_cloud_config()
        cfg.update({
            "provider": "google_drive",
            "registered": True,
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "account_email": account_email,
            "scopes": scopes,
            "client_secret_path": str(cached_secret),
            "token_path": str(self.cloud_token_path()),
        })
        self.save_cloud_config(cfg)
        return cfg

    def ensure_google_drive_credentials(self, parent=None):
        """클라우드 작업 전 등록 여부와 토큰 상태를 확인한다. 실제 Drive API 작업 연결 전 준비 단계."""
        if not self.cloud_token_path().exists():
            QMessageBox.information(
                parent or self,
                self.tr_ui("클라우드 등록 필요"),
                self.tr_ui("Google Drive 계정이 아직 등록되어 있지 않습니다.\n먼저 클라우드 등록을 진행해 주세요."),
            )
            return None
        try:
            InstalledAppFlow, Credentials, Request, build = self.import_google_oauth_modules()
            creds = Credentials.from_authorized_user_file(str(self.cloud_token_path()), ["https://www.googleapis.com/auth/drive.file"])
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(self.cloud_token_path(), "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            return creds
        except Exception as e:
            QMessageBox.warning(parent or self, self.tr_ui("클라우드 연결 확인 실패"), str(e))
            return None

    def cloud_refresh_status_widgets(self, *extra_labels):
        """클라우드 등록/해제 뒤 열린 창의 상태 문구를 즉시 갱신한다."""
        status = self.cloud_status_text()
        labels = list(extra_labels or [])
        for attr in ("_cloud_register_status_label", "_cloud_overview_status_label"):
            lbl = getattr(self, attr, None)
            if lbl is not None:
                labels.append(lbl)
        for lbl in labels:
            try:
                if lbl is not None:
                    if lbl is getattr(self, "_cloud_overview_status_label", None):
                        lbl.setText(
                            self.tr_ui("클라우드 메뉴는 작업환경 캐시 백업/복원과 백업 삭제를 관리합니다.")
                            + "\n"
                            + self.tr_ui("현재 상태")
                            + ": "
                            + status
                        )
                    else:
                        lbl.setText(status)
                    lbl.update()
                    lbl.repaint()
            except Exception:
                pass

        # 같은 클라우드 허브 창을 닫지 않아도 등록/해제 버튼 상태가 즉시 바뀌게 한다.
        registered = self.cloud_is_registered()
        try:
            btn = getattr(self, "_cloud_overview_register_button", None)
            if btn is not None:
                btn.setEnabled(not registered)
                if registered:
                    btn.setToolTip(self.tr_ui("이미 등록된 클라우드 계정이 있어 새 등록을 시작할 수 없습니다. 다른 계정을 연결하려면 먼저 등록 해제를 진행하세요."))
                else:
                    btn.setToolTip("")
                btn.update()
        except Exception:
            pass
        try:
            btn = getattr(self, "_cloud_overview_unregister_button", None)
            if btn is not None:
                btn.setEnabled(registered)
                btn.update()
        except Exception:
            pass

        try:
            if hasattr(self, "launcher_widget"):
                self.launcher_widget.repaint()
        except Exception:
            pass

    def cloud_prompt_password(self, title, message, confirm=False, parent=None):
        """API 키 포함 백업/복원용 암호 입력. 확인용 재입력 옵션 지원."""
        parent = parent or self
        password, ok = QInputDialog.getText(
            parent,
            self.tr_ui(title),
            self.tr_ui(message),
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return None
        password = str(password or "")
        if not password:
            QMessageBox.warning(parent, self.tr_ui(title), self.tr_ui("암호를 비워둘 수 없습니다."))
            return None
        if confirm:
            password2, ok2 = QInputDialog.getText(
                parent,
                self.tr_ui(title),
                self.tr_ui("확인을 위해 암호를 한 번 더 입력하세요."),
                QLineEdit.EchoMode.Password,
            )
            if not ok2:
                return None
            if password != str(password2 or ""):
                QMessageBox.warning(parent, self.tr_ui(title), self.tr_ui("입력한 암호가 서로 다릅니다."))
                return None
        return password

    def cloud_crypto_derive_key(self, password, salt, iterations=200000):
        return hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, int(iterations), dklen=32)

    def cloud_crypto_keystream(self, key, nonce, length):
        out = bytearray()
        counter = 0
        while len(out) < int(length):
            out.extend(hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest())
            counter += 1
        return bytes(out[:length])

    def cloud_crypto_xor(self, data, stream):
        return bytes((a ^ b) for a, b in zip(data, stream))

    def cloud_encrypt_bytes(self, plain_bytes, password):
        """외부 의존성 없는 1차 암호화 컨테이너.
        PBKDF2 + SHA256 기반 keystream + HMAC으로 평문 API 캐시 업로드를 막는다.
        """
        plain_bytes = bytes(plain_bytes or b"")
        salt = os.urandom(16)
        nonce = os.urandom(16)
        iterations = 200000
        key = self.cloud_crypto_derive_key(password, salt, iterations=iterations)
        stream = self.cloud_crypto_keystream(key, nonce, len(plain_bytes))
        cipher = self.cloud_crypto_xor(plain_bytes, stream)
        header = b"YSB-CLOUD-ENC-v1"
        mac = hmac.new(key, header + salt + nonce + cipher, hashlib.sha256).hexdigest()
        payload = {
            "format": "YSB-CLOUD-ENC-v1",
            "kdf": "PBKDF2-HMAC-SHA256",
            "iterations": iterations,
            "cipher": "SHA256-CTR-XOR",
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "hmac": mac,
            "data": base64.b64encode(cipher).decode("ascii"),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def cloud_decrypt_bytes(self, encrypted_bytes, password):
        payload = json.loads(bytes(encrypted_bytes or b"").decode("utf-8"))
        if payload.get("format") != "YSB-CLOUD-ENC-v1":
            raise RuntimeError(self.tr_ui("지원하지 않는 암호화 형식입니다."))
        salt = base64.b64decode(payload.get("salt", ""))
        nonce = base64.b64decode(payload.get("nonce", ""))
        cipher = base64.b64decode(payload.get("data", ""))
        iterations = int(payload.get("iterations", 200000) or 200000)
        key = self.cloud_crypto_derive_key(password, salt, iterations=iterations)
        header = b"YSB-CLOUD-ENC-v1"
        expected = hmac.new(key, header + salt + nonce + cipher, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(payload.get("hmac", ""))):
            raise RuntimeError(self.tr_ui("암호가 틀렸거나 암호화 파일이 손상되었습니다."))
        stream = self.cloud_crypto_keystream(key, nonce, len(cipher))
        return self.cloud_crypto_xor(cipher, stream)

    def read_cloud_backup_manifest(self, zip_path):
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                return json.loads(z.read("manifest.json").decode("utf-8"))
        except Exception:
            return {}

    def reload_runtime_caches_after_cloud_restore(self):
        """클라우드 캐시 복원 후 재시작 없이 즉시 반영 가능한 설정을 다시 읽는다."""
        try:
            self.app_options = load_app_options()
            self.sync_translation_option_cache_to_config()
            self.sync_analysis_mask_options_to_config()

            # v2.4 QA6: 자동저장 모드는 폐지. 클라우드에서 예전 캐시가 복원되어도 강제로 OFF 유지.
            self.auto_save_enabled = False
            self.app_options["auto_save_enabled"] = False

            self.ui_theme = str(self.app_options.get(UI_THEME_KEY, self.ui_theme) or THEME_DARK).lower()
            if self.ui_theme not in (THEME_DARK, THEME_LIGHT):
                self.ui_theme = THEME_DARK
            self.ui_language = normalize_ui_language(self.app_options.get(UI_LANGUAGE_KEY, self.ui_language))
            self.show_paths_in_log = bool(self.app_options.get(SHOW_PATHS_IN_LOG_KEY, False))
            self.show_cache_paths_in_settings = bool(self.app_options.get(SHOW_CACHE_PATHS_IN_SETTINGS_KEY, False))
            self.log_panel_collapsed = bool(self.app_options.get(LOG_PANEL_COLLAPSED_KEY, DEFAULT_LOG_PANEL_COLLAPSED))
            try:
                self.refresh_log_panel_state(save=False)
            except Exception:
                pass

            self.api_settings = ApiSettingsStore.load()
            apply_settings_to_config(self.api_settings)
            try:
                self.restart_engine(show_error=False)
            except Exception:
                pass

            self.shortcut_settings = ShortcutSettingsStore.load()
            self.apply_shortcuts()

            self.load_text_preset_cache()
            self.load_item_text_preset_cache()

            self.apply_theme(self.ui_theme)
            self.apply_language(self.ui_language)
            self.workspace_root = str(get_workspace_root())
            self.log("☁️ 클라우드 캐시 복원 후 런타임 설정을 자동 갱신했습니다.")
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ 클라우드 캐시 자동 갱신 실패: {e}")
            except Exception:
                pass
            return False

    def build_google_drive_service(self, creds):
        """등록된 OAuth 토큰으로 Google Drive API service를 만든다."""
        try:
            InstalledAppFlow, Credentials, Request, build = self.import_google_oauth_modules()
            return build("drive", "v3", credentials=creds)
        except Exception as e:
            raise RuntimeError(f"{self.tr_ui('Google Drive 서비스 생성 실패')}: {e}")

    def import_google_drive_media_modules(self):
        try:
            from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
            return MediaFileUpload, MediaIoBaseDownload
        except Exception as e:
            raise ImportError(
                self.tr_ui("Google Drive 파일 업로드/다운로드 모듈을 불러올 수 없습니다.")
                + f"\n\n{e}"
            )

    def drive_escape_query_text(self, text_value):
        return str(text_value or "").replace("\\", "\\\\").replace("'", "\\'")

    def drive_find_folder(self, service, name, parent_id=None):
        name_q = self.drive_escape_query_text(name)
        q = f"name = '{name_q}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        result = service.files().list(
            q=q,
            spaces="drive",
            fields="files(id,name)",
            pageSize=10,
        ).execute()
        files = result.get("files", []) if isinstance(result, dict) else []
        return files[0] if files else None

    def drive_find_or_create_folder(self, service, name, parent_id=None):
        found = self.drive_find_folder(service, name, parent_id=parent_id)
        if found:
            return found.get("id")
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]
        folder = service.files().create(
            body=metadata,
            fields="id,name",
        ).execute()
        return folder.get("id")

    def ensure_cloud_drive_folders(self, service):
        # 공개 배포판의 Google Drive 연동은 작업환경 캐시 백업/복원 전용이다.
        # YSBT 프로젝트 파일은 사용자가 로컬 파일 또는 동기화 폴더로 직접 관리한다.
        root_id = self.drive_find_or_create_folder(service, "YSB_Translator_Backup")
        cache_id = self.drive_find_or_create_folder(service, "cache_backups", parent_id=root_id)
        cfg = self.load_cloud_config()
        cfg.update({
            "drive_root_folder_id": root_id,
            "drive_cache_folder_id": cache_id,
            "drive_project_folder_id": "",
            "drive_folder_checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.save_cloud_config(cfg)
        return root_id, cache_id, None

    def cloud_backup_manifest(self, backup_type="cache", include_api_keys=False):
        cfg = self.load_cloud_config()
        return {
            "app": "YSB Translator",
            "backup_type": backup_type,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "include_api_keys": bool(include_api_keys),
            "ui_language": getattr(self, "ui_language", LANG_KO),
            "provider": "google_drive",
            "account_email": cfg.get("account_email", ""),
            "format_version": 1,
        }

    def iter_cache_backup_sources(self, include_api_keys=False):
        """백업할 작업환경 캐시 파일 목록을 (실제경로, ZIP 내부경로)로 반환한다.
        API 키 제외가 기본이며, cloud/work_sessions/imported_fonts 같은 임시성/대용량 폴더는 제외한다.
        폰트 파일은 용량과 라이선스 문제를 피하기 위해 캐시 백업에 포함하지 않는다.
        """
        cache_root = get_cache_dir()
        excluded_dirs = {"cloud", "work_sessions", "__pycache__", "recent_thumbnails", "imported_fonts"}
        excluded_files = {
            "google_drive_token.json",
            "cloud_config.json",
            "google_oauth_client_secret.json",
            "api_cache.json",
            "recent_projects.json",
        }

        if cache_root.exists():
            for p in cache_root.rglob("*"):
                if not p.is_file():
                    continue
                try:
                    rel = p.relative_to(cache_root)
                except Exception:
                    continue
                parts = set(rel.parts)
                if parts & excluded_dirs:
                    continue
                if p.name in excluded_files:
                    continue
                yield p, Path("cache") / rel

        # 작업 폴더 위치(workspace_config.json)는 PC별 로컬 설정이다.
        # 다른 PC에서 복원하면 Windows 사용자명이 달라져 경로가 깨질 수 있으므로
        # 클라우드 캐시 백업에는 포함하지 않는다.
        # imported_fonts 폴더의 실제 폰트 파일도 용량/라이선스 문제를 피하기 위해 백업하지 않는다.

    def create_cache_backup_zip(self, include_api_keys=False, api_password=None):
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = self.cloud_dir() / "local_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        zip_path = backup_dir / f"YSB_cache_backup_{ts}.zip"

        manifest = self.cloud_backup_manifest("cache", include_api_keys=include_api_keys)
        if include_api_keys:
            manifest["api_key_encryption"] = "YSB-CLOUD-ENC-v1"
        added = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for src, arc in self.iter_cache_backup_sources(include_api_keys=include_api_keys):
                try:
                    z.write(src, str(arc).replace("\\", "/"))
                    added += 1
                except Exception as e:
                    try:
                        self.log(f"⚠️ 캐시 백업 항목 제외: {src} / {e}")
                    except Exception:
                        pass

            if include_api_keys:
                api_file = get_cache_file("api_cache.json")
                if api_file.exists():
                    if not api_password:
                        raise RuntimeError(self.tr_ui("API 키 포함 백업에는 암호가 필요합니다."))
                    encrypted = self.cloud_encrypt_bytes(api_file.read_bytes(), api_password)
                    z.writestr("secure/api_cache.json.enc", encrypted)
                    added += 1
        if added <= 0:
            raise RuntimeError(self.tr_ui("백업할 캐시 파일을 찾지 못했습니다."))
        return zip_path, added

    def upload_file_to_drive_folder(self, service, local_path, folder_id, mime_type="application/zip"):
        MediaFileUpload, MediaIoBaseDownload = self.import_google_drive_media_modules()
        local_path = Path(local_path)
        metadata = {
            "name": local_path.name,
            "parents": [folder_id],
        }
        media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)
        uploaded = service.files().create(
            body=metadata,
            media_body=media,
            fields="id,name,webViewLink,size,createdTime",
        ).execute()
        return uploaded

    def list_drive_files_in_folder(self, service, folder_id, name_prefix=""):
        q = f"'{folder_id}' in parents and trashed = false"
        if name_prefix:
            q += f" and name contains '{self.drive_escape_query_text(name_prefix)}'"
        files = []
        page_token = None
        while True:
            res = service.files().list(
                q=q,
                spaces="drive",
                fields="nextPageToken, files(id,name,size,createdTime,modifiedTime,webViewLink)",
                orderBy="modifiedTime desc",
                pageSize=50,
                pageToken=page_token,
            ).execute()
            files.extend(res.get("files", []) if isinstance(res, dict) else [])
            page_token = res.get("nextPageToken") if isinstance(res, dict) else None
            if not page_token:
                break
        return files

    def format_drive_time_local(self, iso_text):
        """Google Drive UTC ISO 시간을 현재 PC의 로컬 시간대로 변환해 표시한다.
        내부 정렬/비교에는 Drive의 원본 UTC 값을 유지하고, 사용자 표시만 로컬 시간으로 바꾼다.
        """
        if not iso_text:
            return ""
        try:
            raw = str(iso_text).strip()
            # Google Drive API 예: 2026-05-19T04:11:43.723Z
            dt_utc = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            dt_local = dt_utc.astimezone()  # Windows/OS 현재 시간대 기준
            return dt_local.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(iso_text)

    def format_drive_file_size(self, size_value):
        try:
            n = int(size_value or 0)
        except Exception:
            return str(size_value or "")
        units = ["bytes", "KB", "MB", "GB", "TB"]
        value = float(n)
        idx = 0
        while value >= 1024 and idx < len(units) - 1:
            value /= 1024.0
            idx += 1
        if idx == 0:
            return f"{n} bytes"
        return f"{value:.1f} {units[idx]}"

    def format_drive_backup_label(self, drive_file):
        name = drive_file.get("name", "(no name)") if isinstance(drive_file, dict) else "(no name)"
        iso_time = ""
        size = ""
        if isinstance(drive_file, dict):
            iso_time = drive_file.get("modifiedTime") or drive_file.get("createdTime") or ""
            size = drive_file.get("size", "")
        local_time = self.format_drive_time_local(iso_time)
        size_label = self.format_drive_file_size(size)
        parts = [name]
        if local_time:
            parts.append(local_time)
        if size_label:
            parts.append(size_label)
        return "  /  ".join(parts)

    def choose_drive_backup_file(self, service, folder_id, title, prefix):
        files = self.list_drive_files_in_folder(service, folder_id, name_prefix=prefix)
        if not files:
            QMessageBox.information(
                self,
                self.tr_ui(title),
                self.tr_ui("클라우드에 백업 파일이 없습니다."),
            )
            return None

        labels = []
        mapping = {}
        for f in files:
            label = self.format_drive_backup_label(f)
            labels.append(label)
            mapping[label] = f

        choice, ok = QInputDialog.getItem(
            self,
            self.tr_ui(title),
            self.tr_ui("불러올 백업 파일을 선택하세요."),
            labels,
            0,
            False,
        )
        if not ok or not choice:
            return None
        return mapping.get(choice)

    def download_drive_file(self, service, file_id, local_path):
        MediaFileUpload, MediaIoBaseDownload = self.import_google_drive_media_modules()
        request = service.files().get_media(fileId=file_id)
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        return local_path

    def create_local_restore_safety_backup(self):
        """클라우드 캐시를 덮어쓰기 전에 현재 로컬 캐시를 백업한다."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = self.cloud_dir() / "restore_safety_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        zip_path = backup_dir / f"YSB_local_before_restore_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(self.cloud_backup_manifest("local_before_restore", include_api_keys=False), ensure_ascii=False, indent=2))
            for src, arc in self.iter_cache_backup_sources(include_api_keys=False):
                try:
                    z.write(src, str(arc).replace("\\", "/"))
                except Exception:
                    pass
        return zip_path

    def safe_extract_cache_backup_zip(self, zip_path, apply_api_keys=False, api_password=None):
        """Drive에서 받은 캐시 백업 ZIP을 현재 캐시 폴더에 적용한다."""
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise FileNotFoundError(str(zip_path))

        cache_root = get_cache_dir().resolve()
        config_root = app_config_dir().resolve()

        with zipfile.ZipFile(zip_path, "r") as z:
            manifest = {}
            try:
                manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            except Exception:
                manifest = {}

            if manifest.get("include_api_keys") and not apply_api_keys:
                raise RuntimeError(self.tr_ui("이 백업에는 API 키가 포함되어 있습니다. API 키까지 복원하려면 암호가 필요합니다."))
            if manifest.get("include_api_keys") and apply_api_keys and not api_password:
                raise RuntimeError(self.tr_ui("API 키 포함 백업 복원에는 암호가 필요합니다."))

            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                if not name or name.endswith("/") or name == "manifest.json":
                    continue
                if ".." in Path(name).parts:
                    continue

                if name.startswith("cache/"):
                    rel = Path(name[len("cache/"):])
                    if rel.parts and rel.parts[0] in ("cloud", "work_sessions", "__pycache__", "recent_thumbnails", "imported_fonts"):
                        continue
                    if rel.name == "api_cache.json" and not apply_api_keys:
                        continue
                    dest = (cache_root / rel).resolve()
                    if not str(dest).startswith(str(cache_root)):
                        continue
                elif name.startswith("config/"):
                    # workspace_config.json은 PC별 작업 폴더 경로를 담는다.
                    # A PC에서 만든 백업을 B PC에 복원할 때 사용자명/문서 경로가 달라질 수 있으므로
                    # 기존 백업 ZIP 안에 들어 있어도 복원하지 않고 현재 PC 설정을 유지한다.
                    continue
                else:
                    continue

                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info, "r") as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)

            if manifest.get("include_api_keys") and apply_api_keys:
                try:
                    encrypted_api = z.read("secure/api_cache.json.enc")
                except Exception:
                    encrypted_api = None
                if not encrypted_api:
                    raise RuntimeError(self.tr_ui("암호화된 API 설정 파일을 찾지 못했습니다."))
                plain_api = self.cloud_decrypt_bytes(encrypted_api, api_password)
                api_dest = (cache_root / "api_cache.json").resolve()
                api_dest.parent.mkdir(parents=True, exist_ok=True)
                with open(api_dest, "wb") as f:
                    f.write(plain_api)

        return True

    def format_drive_upload_result_message(self, uploaded, local_path=None, item_count=None):
        parts = [self.tr_ui("클라우드 백업이 완료되었습니다.")]
        if uploaded:
            name = uploaded.get("name", "")
            link = uploaded.get("webViewLink", "")
            if name:
                parts.append(f"\n{self.tr_ui('파일')}: {name}")
            created_local = self.format_drive_time_local(uploaded.get("createdTime", ""))
            if created_local:
                parts.append(f"\n{self.tr_ui('백업 시간')}: {created_local}")
            if link:
                parts.append(f"\n{self.tr_ui('링크')}: {link}")
        if item_count is not None:
            parts.append(f"\n{self.tr_ui('백업 항목')}: {item_count}")
        if local_path:
            parts.append(f"\n{self.tr_ui('로컬 백업 파일')}: {local_path}")
        return "\n".join(parts)

    def _cloud_action_dialog(self, title, description, action_text=None, action_callback=None, extra_builder=None, min_width=760, min_height=360):
        """클라우드 메뉴/허브에서 공통으로 쓰는 개별 동작 창.
        메뉴에서 직접 눌러도 이 전용 창이 뜨고, 허브에서 눌러도 같은 창이 뜬다.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui(title))
        dlg.resize(min_width, min_height)
        try:
            dlg.setStyleSheet(self.settings_dialog_style())
        except Exception:
            pass

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title_label = QLabel(self.tr_ui(title), dlg)
        title_label.setObjectName("SettingsDialogTitle")
        root.addWidget(title_label)

        desc_label = QLabel(self.tr_ui(description), dlg)
        desc_label.setObjectName("SettingsDescription")
        desc_label.setWordWrap(True)
        root.addWidget(desc_label)

        content = QFrame(dlg)
        content.setObjectName("SettingsBlock")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 14, 16, 14)
        content_layout.setSpacing(10)
        root.addWidget(content, 1)

        context = {}
        if callable(extra_builder):
            try:
                extra_builder(content_layout, dlg, context)
            except TypeError:
                extra_builder(content_layout, dlg)

        content_layout.addStretch(1)

        btns = QDialogButtonBox(dlg)
        if action_text and callable(action_callback):
            run_btn = btns.addButton(self.tr_ui(action_text), QDialogButtonBox.ButtonRole.AcceptRole)
            try:
                run_btn.setAutoDefault(True)
                run_btn.setDefault(True)
            except Exception:
                pass
            def _run():
                action_callback(dlg, context)
            run_btn.clicked.connect(_run)
        close_btn = btns.addButton(self.tr_ui("닫기"), QDialogButtonBox.ButtonRole.RejectRole)
        close_btn.clicked.connect(dlg.reject)
        root.addWidget(btns)
        dlg.exec()

    def _cloud_info_row(self, layout, title, description):
        item = QFrame()
        item.setObjectName("SettingsItem")
        item_layout = QVBoxLayout(item)
        item_layout.setContentsMargins(12, 10, 12, 10)
        item_layout.setSpacing(4)
        t = QLabel(self.tr_ui(title), item)
        t.setObjectName("SettingsItemTitle")
        item_layout.addWidget(t)
        d = QLabel(self.tr_ui(description), item)
        d.setObjectName("SettingsDescription")
        d.setWordWrap(True)
        item_layout.addWidget(d)
        layout.addWidget(item)
        return d

    def _show_cloud_placeholder(self, title, message, parent=None):
        self.show_ok_notice(title, message, parent=parent or self)

    def cloud_register(self):
        if self.cloud_is_registered():
            self.show_ok_notice(
                "클라우드 등록",
                "이미 Google Drive 계정이 등록되어 있습니다.\n\n다른 계정을 연결하려면 먼저 클라우드 등록 해제를 진행해 주세요.",
                parent=self,
            )
            return

        def build(layout, dlg, ctx):
            self._cloud_info_row(
                layout,
                "연결 대상",
                "Google Drive 계정을 OAuth로 연결합니다. 등록 버튼을 누르면 브라우저가 열리고, Google 로그인/권한 허용을 완료하면 로컬 토큰이 저장됩니다.",
            )
            status_label = self._cloud_info_row(
                layout,
                "현재 상태",
                self.cloud_status_text(),
            )
            ctx["cloud_status_label"] = status_label
            self._cloud_register_status_label = status_label
            self._cloud_info_row(
                layout,
                "보안 안내",
                "OAuth 토큰은 현재 PC의 로컬 캐시에 저장됩니다. 등록 해제 시 이 토큰을 삭제합니다. Google OAuth 클라이언트 JSON은 Drive API 로그인 시작에만 사용됩니다.",
            )

            cfg = self.load_cloud_config()
            detected_secret = self.find_default_cloud_client_secret()
            cached_secret = str(cfg.get("client_secret_path") or "")
            if cached_secret and self.is_valid_google_oauth_client_secret(cached_secret):
                detected_secret = cached_secret
            if detected_secret:
                ctx["client_secret_path"] = detected_secret
                oauth_desc = "OAuth 설정이 준비되어 있습니다. Google 로그인 버튼을 누르면 브라우저에서 Google 계정 연결을 시작합니다."
            else:
                oauth_desc = "OAuth 설정을 찾지 못했습니다. 배포본에 cloud_oauth_client.json이 포함되어 있는지 확인해 주세요."

            self._cloud_info_row(
                layout,
                "Google 로그인",
                oauth_desc,
            )

        def run(dlg, ctx):
            client_secret_path = str(ctx.get("client_secret_path") or "") or self.find_default_cloud_client_secret()
            if not client_secret_path:
                self.show_ok_notice(
                    "클라우드 등록",
                    "Google OAuth 설정이 없어 로그인을 시작할 수 없습니다. 배포본에 cloud_oauth_client.json이 포함되어 있는지 확인해 주세요.",
                    parent=dlg,
                )
                return

            if not self.ask_yes_no_shortcut(
                "클라우드 등록",
                "브라우저를 열어 Google Drive 로그인을 시작할까요?",
                yes_text="로그인",
                no_text="취소",
                default_yes=True,
                icon=QMessageBox.Icon.Question,
                parent=dlg,
            ):
                return

            try:
                cfg = self.run_google_drive_oauth(client_secret_path, parent=dlg)
            except CloudOAuthCancelled as e:
                self.show_ok_notice(
                    "클라우드 등록 취소",
                    str(e) or "클라우드 등록이 취소되었습니다.",
                    parent=dlg,
                )
                return
            except ImportError as e:
                QMessageBox.warning(dlg, self.tr_ui("클라우드 등록 준비 필요"), str(e))
                return
            except Exception as e:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("클라우드 등록 실패"),
                    self.tr_ui("Google Drive 계정 등록에 실패했습니다.") + f"\n\n{e}",
                )
                return

            self.cloud_refresh_status_widgets(ctx.get("cloud_status_label"))
            account = str(cfg.get("account_email") or "").strip()
            msg = "Google Drive 계정 등록이 완료되었습니다."
            if account:
                msg += f"\n\n{account}"
            self.show_ok_notice("클라우드 등록 완료", msg, parent=dlg)
            try:
                self.log(f"☁️ 클라우드 등록 완료: {account or 'Google Drive'}")
            except Exception:
                pass

        self._cloud_action_dialog(
            "클라우드 등록",
            "클라우드 백업/불러오기를 사용하려면 먼저 Google Drive 계정을 연결해야 합니다.",
            "Google 로그인",
            run,
            build,
            min_height=520,
        )

    def cloud_unregister(self):
        def build(layout, dlg, ctx):
            status_label = self._cloud_info_row(
                layout,
                "현재 상태",
                self.cloud_status_text(),
            )
            ctx["cloud_status_label"] = status_label
            self._cloud_register_status_label = status_label
            self._cloud_info_row(
                layout,
                "해제 범위",
                "현재 PC에 저장된 Google Drive OAuth 토큰과 클라우드 설정 캐시를 삭제합니다. 이후 클라우드 백업/복원 기능은 다시 등록해야 사용할 수 있습니다.",
            )
            self._cloud_info_row(
                layout,
                "주의",
                "등록 해제는 로컬 연결 정보를 지우는 작업입니다. 클라우드에 이미 올라간 백업 파일은 별도 삭제하지 않습니다.",
            )
        def run(dlg, ctx):
            if not self.ask_yes_no_shortcut(
                "클라우드 등록 해제",
                "클라우드 등록을 해제할까요?",
                yes_text="해제",
                no_text="취소",
                default_yes=False,
                icon=QMessageBox.Icon.Warning,
                parent=dlg,
            ):
                return

            # 등록 해제는 로컬 상태 삭제가 본작업이다.
            # Google revoke 네트워크 요청을 먼저 실행하면 간헐적으로 UI가 멈춘 것처럼 보일 수 있으므로,
            # 토큰 원문만 잠깐 보관한 뒤 로컬 파일을 즉시 삭제하고 화면을 먼저 갱신한다.
            token_json_text = ""
            try:
                token_path = self.cloud_token_path()
                if token_path.exists():
                    token_json_text = token_path.read_text(encoding="utf-8")
            except Exception:
                token_json_text = ""

            removed = []
            for p in (self.cloud_token_path(), self.cloud_config_path(), self.cloud_client_secret_path()):
                try:
                    if p.exists():
                        p.unlink()
                        removed.append(str(p))
                except Exception as e:
                    try:
                        self.log(f"⚠️ 클라우드 연결 정보 삭제 실패: {p} / {e}")
                    except Exception:
                        pass

            self.cloud_refresh_status_widgets(ctx.get("cloud_status_label"))
            self.show_ok_notice(
                "클라우드 등록 해제",
                "Google Drive 계정 연결이 해제되었습니다.",
                parent=dlg,
            )
            try:
                self.log("☁️ 클라우드 등록 해제 완료")
            except Exception:
                pass

            # Google 서버 쪽 토큰 revoke는 보조 작업이다. 실패해도 로컬 등록 해제는 성공으로 본다.
            if token_json_text:
                def _best_effort_revoke(token_text):
                    try:
                        InstalledAppFlow, Credentials, Request, build = self.import_google_oauth_modules()
                        info = json.loads(token_text)
                        creds = Credentials.from_authorized_user_info(info, ["https://www.googleapis.com/auth/drive.file"])
                        creds.revoke(Request())
                    except Exception:
                        pass
                try:
                    threading.Thread(target=_best_effort_revoke, args=(token_json_text,), daemon=True).start()
                except Exception:
                    pass

        self._cloud_action_dialog(
            "클라우드 등록 해제",
            "이 PC에서 클라우드 연결을 끊는 전용 창입니다.",
            "해제",
            run,
            build,
        )

    def cloud_backup_cache(self):

        def build(layout, dlg, ctx):
            self._cloud_info_row(
                layout,
                "백업 대상",
                "옵션, 단축키, 매크로, 글꼴 프리셋, 번역 프롬프트, 단어장 같은 작업환경 캐시를 클라우드에 백업합니다. 불러온 폰트 파일 자체는 용량과 라이선스 문제를 피하기 위해 백업하지 않습니다.",
            )
            api_box = QFrame(dlg)
            api_box.setObjectName("SettingsItem")
            api_layout = QVBoxLayout(api_box)
            api_layout.setContentsMargins(12, 10, 12, 10)
            api_layout.setSpacing(6)
            cb = QCheckBox(self.tr_ui("API 키까지 백업"), api_box)
            cb.setToolTip(self.tr_ui("API 키는 유료 API 접근 정보일 수 있으므로, 선택한 경우 암호화가 필수입니다."))
            api_layout.addWidget(cb)
            ctx["include_api_keys_checkbox"] = cb
            api_desc = QLabel(self.tr_ui("기본값은 API 키 제외입니다. API 키까지 백업을 체크하면 업로드 전 반드시 암호화하고, 클라우드에서 불러올 때 반드시 복호화합니다. 암호화/복호화가 준비되지 않은 상태에서는 API 키 포함 백업을 실행하지 않습니다."), api_box)
            api_desc.setObjectName("SettingsDescription")
            api_desc.setWordWrap(True)
            api_layout.addWidget(api_desc)
            layout.addWidget(api_box)
            self._cloud_info_row(
                layout,
                "보안 규칙",
                "API 키는 평문으로 클라우드에 올리지 않습니다. API 키 포함 백업은 암호화 ZIP 또는 암호화된 별도 파일로 저장하고, 불러오기 단계에서 복호화 후 적용합니다.",
            )
        def run(dlg, ctx):
            cb = ctx.get("include_api_keys_checkbox")
            include_api = bool(cb.isChecked()) if cb is not None else False
            question = "현재 작업환경 캐시를 클라우드로 백업할까요?"
            if include_api:
                question = "API 키까지 포함하여 작업환경 캐시를 클라우드로 백업할까요? API 키는 업로드 전에 반드시 암호화됩니다."
            if not self.ask_yes_no_shortcut(
                "클라우드로 캐시 백업",
                question,
                yes_text="백업",
                no_text="취소",
                default_yes=True,
                icon=QMessageBox.Icon.Warning if include_api else QMessageBox.Icon.Question,
                parent=dlg,
            ):
                return
            creds = self.ensure_google_drive_credentials(parent=dlg)
            if creds is None:
                return
            api_password = None
            if include_api:
                api_password = self.cloud_prompt_password(
                    "API 키 포함 캐시 백업",
                    "API 키를 암호화할 암호를 입력하세요. 이 암호를 잊으면 API 키 포함 백업은 복원할 수 없습니다.",
                    confirm=True,
                    parent=dlg,
                )
                if not api_password:
                    return
            try:
                service = self.build_google_drive_service(creds)
                root_id, cache_folder_id, project_folder_id = self.ensure_cloud_drive_folders(service)
                zip_path, item_count = self.create_cache_backup_zip(include_api_keys=include_api, api_password=api_password)
                uploaded = self.upload_file_to_drive_folder(service, zip_path, cache_folder_id, mime_type="application/zip")
            except Exception as e:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("클라우드로 캐시 백업 실패"),
                    self.tr_ui("캐시 백업을 클라우드에 올리지 못했습니다.") + f"\n\n{e}",
                )
                return
            self.show_ok_notice(
                "클라우드로 캐시 백업 완료",
                self.format_drive_upload_result_message(uploaded, local_path=str(zip_path), item_count=item_count),
                parent=dlg,
            )
            try:
                self.log(f"☁️ 캐시 백업 업로드 완료: {uploaded.get('name', '')}")
            except Exception:
                pass
        self._cloud_action_dialog(
            "클라우드로 캐시 백업",
            "현재 PC의 작업환경 캐시를 클라우드에 올리는 전용 창입니다. API 키는 별도 체크한 경우에만 포함하며, 포함 시 암호화가 필수입니다.",
            "백업",
            run,
            build,
            min_height=470,
        )

    def cloud_restore_cache(self):
        def build(layout, dlg, ctx):
            self._cloud_info_row(
                layout,
                "불러오기 대상",
                "클라우드에 저장된 작업환경 캐시를 내려받아 현재 PC에 적용합니다. 실제 적용 전에는 현재 로컬 설정을 먼저 백업합니다.",
            )
            self._cloud_info_row(
                layout,
                "API 키 복호화 규칙",
                "백업에 API 키가 포함되어 있다면 반드시 복호화 과정을 거친 뒤에만 적용합니다. 복호화에 실패하면 API 키는 적용하지 않고, 기존 로컬 API 설정을 보호합니다.",
            )
            self._cloud_info_row(
                layout,
                "주의",
                "캐시 불러오기는 단축키, 프리셋, 옵션 같은 현재 작업환경을 바꿀 수 있습니다. 적용 전 확인창을 한 번 더 표시합니다.",
            )
        def run(dlg, ctx):
            if not self.ask_yes_no_shortcut(
                "클라우드에서 캐시 불러오기",
                "클라우드에 저장된 작업환경 캐시를 불러올까요? 현재 로컬 설정을 덮어쓸 수 있습니다.",
                yes_text="불러오기",
                no_text="취소",
                default_yes=True,
                icon=QMessageBox.Icon.Warning,
                parent=dlg,
            ):
                return
            creds = self.ensure_google_drive_credentials(parent=dlg)
            if creds is None:
                return
            try:
                service = self.build_google_drive_service(creds)
                root_id, cache_folder_id, project_folder_id = self.ensure_cloud_drive_folders(service)
                selected = self.choose_drive_backup_file(service, cache_folder_id, "클라우드에서 캐시 불러오기", "YSB_cache_backup_")
                if not selected:
                    return
                if not self.ask_yes_no_shortcut(
                    "클라우드에서 캐시 불러오기",
                    f"{selected.get('name', '')}\n\n이 백업을 내려받아 현재 로컬 설정에 적용할까요?\n적용 전 현재 로컬 캐시는 안전 백업으로 저장됩니다.",
                    yes_text="적용",
                    no_text="취소",
                    default_yes=False,
                    icon=QMessageBox.Icon.Warning,
                    parent=dlg,
                ):
                    return
                safety = self.create_local_restore_safety_backup()
                download_dir = self.cloud_dir() / "downloads"
                download_dir.mkdir(parents=True, exist_ok=True)
                local_zip = download_dir / selected.get("name", "cloud_cache_backup.zip")
                self.download_drive_file(service, selected.get("id"), local_zip)
                manifest = self.read_cloud_backup_manifest(local_zip)
                apply_api = bool(manifest.get("include_api_keys"))
                api_password = None
                if apply_api:
                    api_password = self.cloud_prompt_password(
                        "API 키 포함 캐시 불러오기",
                        "이 백업에는 암호화된 API 설정이 포함되어 있습니다. 복호화 암호를 입력하세요.",
                        confirm=False,
                        parent=dlg,
                    )
                    if not api_password:
                        return
                self.safe_extract_cache_backup_zip(local_zip, apply_api_keys=apply_api, api_password=api_password)
                self.reload_runtime_caches_after_cloud_restore()
            except Exception as e:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("클라우드에서 캐시 불러오기 실패"),
                    self.tr_ui("클라우드 캐시 백업을 적용하지 못했습니다.") + f"\n\n{e}",
                )
                return
            self.show_ok_notice(
                "클라우드에서 캐시 불러오기 완료",
                "클라우드 캐시 백업을 적용하고 가능한 설정을 즉시 갱신했습니다.\n\n"
                + self.tr_ui("현재 로컬 설정 안전 백업")
                + f": {safety}\n"
                + self.tr_ui("작업 폴더 위치가 바뀐 백업이라면 재시작 후 완전히 반영됩니다."),
                parent=dlg,
            )
            try:
                self.log(f"☁️ 캐시 백업 복원 완료: {selected.get('name', '')}")
            except Exception:
                pass
        self._cloud_action_dialog(
            "클라우드에서 캐시 불러오기",
            "클라우드에 저장된 작업환경 캐시를 내려받아 현재 PC에 적용하는 전용 창입니다.",
            "불러오기",
            run,
            build,
            min_height=450,
        )

    def delete_drive_file_permanently(self, service, file_id):
        service.files().delete(fileId=file_id).execute()

    def cloud_delete_cache_backups(self):
        def build(layout, dlg, ctx):
            self._cloud_info_row(
                layout,
                "삭제 대상",
                "Google Drive의 YSB_Translator_Backup/cache_backups 폴더에 저장된 작업환경 캐시 백업 ZIP만 삭제합니다. 프로젝트 파일은 공개 배포판 클라우드 백업 대상이 아닙니다.",
            )
            self._cloud_info_row(
                layout,
                "전체 백업 삭제",
                "클라우드에 있는 캐시 백업을 전부 삭제합니다. 이 작업은 되돌릴 수 없습니다.",
            )
            self._cloud_info_row(
                layout,
                "최신본만 남기기",
                "가장 최근에 수정된 캐시 백업 1개만 남기고 나머지 캐시 백업을 삭제합니다.",
            )

        def run(dlg, ctx):
            mode, ok = QInputDialog.getItem(
                dlg,
                self.tr_ui("클라우드 백업 삭제"),
                self.tr_ui("삭제 방식을 선택하세요."),
                [
                    self.tr_ui("최신 백업 1개만 남기고 삭제"),
                    self.tr_ui("전체 백업 삭제"),
                ],
                0,
                False,
            )
            if not ok or not mode:
                return

            creds = self.ensure_google_drive_credentials(parent=dlg)
            if creds is None:
                return

            try:
                service = self.build_google_drive_service(creds)
                root_id, cache_folder_id, _ = self.ensure_cloud_drive_folders(service)
                files = self.list_drive_files_in_folder(service, cache_folder_id, name_prefix="YSB_cache_backup_")
            except Exception as e:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("클라우드 백업 삭제 실패"),
                    self.tr_ui("클라우드 백업 목록을 불러오지 못했습니다.") + f"\n\n{e}",
                )
                return

            if not files:
                QMessageBox.information(
                    dlg,
                    self.tr_ui("클라우드 백업 삭제"),
                    self.tr_ui("삭제할 클라우드 캐시 백업이 없습니다."),
                )
                return

            delete_all = mode == self.tr_ui("전체 백업 삭제")
            if delete_all:
                targets = list(files)
                question = self.tr_ui("클라우드의 캐시 백업을 전부 삭제할까요?\n\n삭제 개수: {count}개\n이 작업은 되돌릴 수 없습니다.").format(count=len(targets))
            else:
                files_sorted = sorted(files, key=lambda f: str(f.get("modifiedTime") or f.get("createdTime") or ""), reverse=True)
                keep = files_sorted[0] if files_sorted else None
                targets = files_sorted[1:]
                if not targets:
                    QMessageBox.information(
                        dlg,
                        self.tr_ui("클라우드 백업 삭제"),
                        self.tr_ui("이미 최신 백업 1개만 남아 있습니다."),
                    )
                    return
                question = (
                    self.tr_ui("최신 캐시 백업 1개만 남기고 나머지를 삭제할까요?")
                    + "\n\n"
                    + self.tr_ui("남길 백업")
                    + f": {keep.get('name', '')}\n"
                    + self.tr_ui("삭제 개수")
                    + f": {len(targets)}개\n"
                    + self.tr_ui("이 작업은 되돌릴 수 없습니다.")
                )

            if not self.ask_yes_no_shortcut(
                "클라우드 백업 삭제",
                question,
                yes_text="삭제",
                no_text="취소",
                default_yes=False,
                icon=QMessageBox.Icon.Warning,
                parent=dlg,
            ):
                return

            deleted = 0
            errors = []
            for f in targets:
                try:
                    self.delete_drive_file_permanently(service, f.get("id"))
                    deleted += 1
                except Exception as e:
                    errors.append(f"{f.get('name', '')}: {e}")

            if errors:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("클라우드 백업 삭제 일부 실패"),
                    self.tr_ui("일부 백업을 삭제하지 못했습니다.")
                    + f"\n\n{self.tr_ui('삭제 성공')}: {deleted}개\n"
                    + "\n".join(errors[:10]),
                )
            else:
                self.show_ok_notice(
                    "클라우드 백업 삭제 완료",
                    self.tr_ui("클라우드 캐시 백업 삭제가 완료되었습니다.") + f"\n\n{self.tr_ui('삭제 개수')}: {deleted}개",
                    parent=dlg,
                )
            try:
                self.log(f"☁️ 클라우드 캐시 백업 삭제 완료: {deleted}개")
            except Exception:
                pass

        self._cloud_action_dialog(
            "클라우드 백업 삭제",
            "Google Drive에 저장된 작업환경 캐시 백업을 정리하는 전용 창입니다. 전체 삭제 또는 최신본 1개만 남기기를 선택할 수 있습니다.",
            "백업 삭제",
            run,
            build,
            min_height=470,
        )

    def cloud_backup_current_project(self):
        # 공개 배포판에서는 Google Drive 프로젝트 백업 기능을 제공하지 않는다.
        QMessageBox.information(
            self,
            self.tr_ui("기능 제거됨"),
            self.tr_ui("공개 배포판에서는 Google Drive 프로젝트 백업을 사용하지 않습니다. 프로젝트 파일은 로컬 파일 또는 사용자의 동기화 폴더로 직접 관리해 주세요."),
        )

    def cloud_restore_project_from_cloud(self):
        # 공개 배포판에서는 Google Drive 프로젝트 불러오기 기능을 제공하지 않는다.
        QMessageBox.information(
            self,
            self.tr_ui("기능 제거됨"),
            self.tr_ui("공개 배포판에서는 클라우드에서 프로젝트 불러오기를 사용하지 않습니다. 프로젝트 파일은 로컬 파일 또는 사용자의 동기화 폴더로 직접 관리해 주세요."),
        )

    def open_cloud_overview_dialog(self, include_project_backup=None):
        """홈화면/런처에서 쓰는 클라우드 허브 창.
        공개 배포판에서는 Google Drive 연동을 작업환경 캐시 백업/복원 전용으로 유지한다.
        include_project_backup 인자는 이전 버전 호환용으로만 남겨두며 사용하지 않는다.
        """
        include_project_backup = False

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("클라우드"))
        dlg.resize(800, 660)
        try:
            dlg.setStyleSheet(self.settings_dialog_style())
        except Exception:
            pass

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel(self.tr_ui("클라우드"), dlg)
        title.setObjectName("SettingsDialogTitle")
        root.addWidget(title)

        intro = QLabel(self.tr_ui("클라우드 메뉴는 작업환경 캐시 백업/복원과 백업 삭제를 관리합니다.") + "\n" + self.tr_ui("현재 상태") + ": " + self.cloud_status_text(), dlg)
        intro.setObjectName("SettingsDescription")
        intro.setWordWrap(True)
        self._cloud_overview_status_label = intro
        root.addWidget(intro)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(scroll)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        cloud_block, cloud_layout = self._settings_block(
            "클라우드",
            "Google Drive와 연결해 작업환경 캐시를 보존하고, 필요할 때 다시 불러오거나 오래된 백업을 정리하는 영역입니다.",
        )

        def add_cloud_item(title_text, description_text, button_text, slot):
            item = QFrame(dlg)
            item.setObjectName("SettingsItem")
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(12, 10, 12, 10)
            item_layout.setSpacing(12)
            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            text_box.setSpacing(4)
            t = QLabel(self.tr_ui(title_text), item)
            t.setObjectName("SettingsItemTitle")
            text_box.addWidget(t)
            d = QLabel(self.tr_ui(description_text), item)
            d.setObjectName("SettingsDescription")
            d.setWordWrap(True)
            text_box.addWidget(d)
            item_layout.addLayout(text_box, 1)
            btn = QPushButton(self.tr_ui(button_text), item)
            btn.setMinimumWidth(150)
            try:
                registered = self.cloud_is_registered()
                if title_text == "클라우드 등록":
                    self._cloud_overview_register_button = btn
                    if registered:
                        btn.setEnabled(False)
                        btn.setToolTip(self.tr_ui("이미 등록된 클라우드 계정이 있어 새 등록을 시작할 수 없습니다. 다른 계정을 연결하려면 먼저 등록 해제를 진행하세요."))
                elif title_text == "클라우드 등록 해제":
                    self._cloud_overview_unregister_button = btn
                    btn.setEnabled(registered)
            except Exception:
                pass
            btn.clicked.connect(slot)
            item_layout.addWidget(btn, 0)
            cloud_layout.addWidget(item)

        add_cloud_item(
            "클라우드 등록",
            "Google Drive 계정을 연결합니다. 등록 후 작업환경 캐시 백업, 캐시 불러오기, 백업 삭제 기능을 사용할 수 있게 됩니다.",
            "등록",
            self.cloud_register,
        )
        add_cloud_item(
            "클라우드 등록 해제",
            "현재 PC에 저장된 클라우드 연결 토큰을 해제합니다. 이후 백업/불러오기 기능은 다시 등록해야 사용할 수 있습니다.",
            "해제",
            self.cloud_unregister,
        )
        add_cloud_item(
            "클라우드로 캐시 백업",
            "옵션, 단축키, 매크로, 프리셋, 프롬프트, 단어장 같은 작업환경 캐시를 백업합니다. 불러온 폰트 파일 자체는 백업하지 않습니다. API 키는 체크박스로 별도 선택하며, 포함 시 업로드 전 암호화와 불러오기 시 복호화가 필수입니다.",
            "캐시 백업",
            self.cloud_backup_cache,
        )
        add_cloud_item(
            "클라우드에서 캐시 불러오기",
            "클라우드에 저장된 작업환경 캐시를 내려받아 현재 PC에 적용합니다. API 키가 포함된 백업은 복호화 후에만 적용합니다.",
            "캐시 불러오기",
            self.cloud_restore_cache,
        )
        add_cloud_item(
            "클라우드 백업 삭제",
            "클라우드에 저장된 작업환경 캐시 백업을 정리합니다. 전체 백업 삭제 또는 최신 백업 1개만 남기기를 선택할 수 있습니다.",
            "백업 삭제",
            self.cloud_delete_cache_backups,
        )

        body_layout.addWidget(cloud_block)
        body_layout.addStretch(1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        btns.button(QDialogButtonBox.StandardButton.Close).setText(self.tr_ui("닫기"))
        btns.rejected.connect(dlg.reject)
        root.addWidget(btns)
        dlg.exec()

