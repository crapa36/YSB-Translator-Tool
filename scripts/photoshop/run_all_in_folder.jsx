#target photoshop
app.displayDialogs = DialogModes.NO;

// ===== 설정 =====
// 1) 여기를 네가 원하는 "스크립트 폴더"로 바꿔도 되고,
// 2) 그냥 실행 시 폴더 선택 팝업을 띄우게(아래 USE_PICKER=true) 써도 됨.
var USE_PICKER = true;

// 고정 경로를 쓰고 싶으면 USE_PICKER=false 로 바꾸고 PATH를 채워.
var PATH = "C:/YOUR/SCRIPTS/FOLDER"; // Windows 예시
// var PATH = "/Users/yourname/ScriptsFolder"; // macOS 예시

// 실행 순서 정렬: "name" (파일명 오름차순) / "none"(그대로)
var SORT_MODE = "name";

// 하위 스크립트에서 뜨는 alert()를 막고, 마지막 요약 알림만 띄울지 여부
var SUPPRESS_CHILD_ALERTS = true;

// 실행 제외 규칙(원하면 확장)
var SKIP_FILES = {
  "run_all_in_folder.jsx": true,             // 기존 자기 자신
  "run_all_in_folder_final_alert.jsx": true, // 수정본 자기 자신
  "_ignore.jsx": true
};
// =================

// 최종 알림용 원본 alert 보관
var ORIGINAL_ALERT = alert;
var suppressedAlertCount = 0;
var suppressedAlertLogs = [];

function finalAlert(msg) {
  ORIGINAL_ALERT(msg);
}

function pickFolderOrDie() {
  var f = Folder.selectDialog("실행할 스크립트(.jsx)들이 들어있는 폴더를 선택하세요");
  if (!f) throw new Error("폴더 선택이 취소되었습니다.");
  return f;
}

function getFolderOrDie() {
  var folder = USE_PICKER ? pickFolderOrDie() : new Folder(PATH);
  if (!folder.exists) throw new Error("폴더가 존재하지 않습니다: " + folder.fsName);
  return folder;
}

function isSelfFile(f) {
  try {
    var selfFile = new File($.fileName);
    return f.fsName === selfFile.fsName;
  } catch (e) {
    return false;
  }
}

function listJsxFiles(folder) {
  // .jsx / .jsxbin 둘 다 잡고 싶으면 여기서 조건 추가 가능
  var files = folder.getFiles(function (f) {
    if (!(f instanceof File)) return false;
    if (isSelfFile(f)) return false;

    var name = f.name;
    var lower = name.toLowerCase();

    if (SKIP_FILES[name]) return false;
    return lower.match(/\.jsx$/) !== null;
  });

  if (SORT_MODE === "name") {
    files.sort(function(a,b){
      var an = a.name.toLowerCase();
      var bn = b.name.toLowerCase();
      return an < bn ? -1 : (an > bn ? 1 : 0);
    });
  }
  return files;
}

function makeChildAlert(scriptName) {
  return function (msg) {
    suppressedAlertCount++;
    suppressedAlertLogs.push(scriptName + " => " + String(msg));
    $.writeln("SUPPRESSED ALERT [" + scriptName + "]: " + String(msg));
  };
}

function runFile(f) {
  $.writeln("RUN: " + f.fsName);

  if (!SUPPRESS_CHILD_ALERTS) {
    $.evalFile(f);
    return;
  }

  var previousAlert = alert;

  try {
    // 하위 스크립트의 성공 alert()를 여기서 가로채서 팝업이 안 뜨게 함
    alert = makeChildAlert(f.name);
    $.evalFile(f);
  } finally {
    // 실패/중단이 나도 반드시 원래 alert로 복구
    alert = previousAlert;
  }
}

(function main(){
  try {
    var folder = getFolderOrDie();
    var files = listJsxFiles(folder);

    if (!files || files.length === 0) {
      finalAlert("폴더에 실행할 .jsx 파일이 없습니다:\n" + folder.fsName);
      return;
    }

    // 실행 로그 요약용
    var ok = 0;
    var fail = 0;
    var failed = [];

    for (var i = 0; i < files.length; i++) {
      try {
        runFile(files[i]);
        ok++;
      } catch (e) {
        fail++;
        failed.push(files[i].name + " => " + e.message);
        // 실패해도 계속 진행하고 싶으면 유지, 즉시 중단하고 싶으면 throw e;
      }
    }

    var msg = "완료"
      + "\n실행 대상: " + files.length
      + "\n성공: " + ok
      + "\n실패: " + fail;

    if (SUPPRESS_CHILD_ALERTS) {
      msg += "\n차단한 개별 알림: " + suppressedAlertCount;
    }

    if (failed.length) {
      msg += "\n\n실패 목록:\n- " + failed.join("\n- ");
    }

    finalAlert(msg);

  } catch (e) {
    finalAlert("중단됨: " + e.message);
  }
})();
