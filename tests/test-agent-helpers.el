;;; test-agent-helpers.el --- ERT tests for agent-helpers -*- lexical-binding: t; -*-

;; Run with:
;;   emacs --batch -Q \
;;     -l ert \
;;     -l container/agent-helpers.el \
;;     -l tests/test-agent-helpers.el \
;;     -f ert-run-tests-batch-and-exit

(require 'ert)
(require 'org)
(require 'cl-lib)
(require 'json)

(defvar test-agent-helpers--keyword-header
  "#+TODO: TODO(t) PROJ(p) NEXT(n) INPROGRESS(i!) WAITING(w) SOMEDAY(s) | DONE(d!) CANCELLED(c) OBSOLETE(o)\n\n"
  "TODO keyword declaration used by test fixtures.

Mirrors the keyword set the host Emacs config defines, so a state that does
not exist in real projects cannot pass here. It previously declared
BLOCKED(b), which made a state agents were told to use look supported while
every real call failed.

INPROGRESS and DONE keep a logging flag because durations are read from the
logged state lines and need both endpoints. Production uses `DONE(d@)', which
timestamps too; the fixture uses `!' to avoid the note machinery. A keyword
with no flag at all (`TODO(t)', `PROJ(p)') logs nothing, so an INPROGRESS ->
TODO transition leaves a span with no end — absent, not wrong.")

;; Tests must never append to the real stash worklog by default. Worklog-specific
;; coverage binds this to a temp directory with `test-agent-helpers--with-worklog'.
(setq bergheim/agent-worklog-dir nil)

(defmacro test-agent-helpers--with-file (body-string &rest body)
  "Create a temp org file containing BODY-STRING (prefixed with the keyword
header), bind its path to `test-file', and kill the buffer afterward."
  (declare (indent 1))
  `(let* ((test-file (make-temp-file "agent-helpers-test-" nil ".org"))
          (inhibit-message t))
     (unwind-protect
         (progn
           (with-temp-file test-file
             (insert test-agent-helpers--keyword-header)
             (insert ,body-string))
           ,@body)
       (dolist (buf (buffer-list))
         (when (and (buffer-file-name buf)
                    (string= (file-truename (buffer-file-name buf))
                             (file-truename test-file)))
           (with-current-buffer buf
             (set-buffer-modified-p nil))
           (kill-buffer buf)))
       (ignore-errors (delete-file test-file)))))

(defun test-agent-helpers--contents (file)
  "Read FILE contents into a string."
  (with-temp-buffer
    (insert-file-contents file)
    (buffer-string)))

(defun test-agent-helpers--json-read (string)
  "Parse STRING as JSON using predictable alist/list containers."
  (let ((json-object-type 'alist)
        (json-array-type 'list)
        (json-key-type 'symbol))
    (json-read-from-string string)))

;; ----------------------------------------------------------------------------
;; Existing set-state behavior (should keep passing)
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/set-state-basic ()
  "`set-state' transitions TODO to DONE."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "DONE")
    (should (string-match-p "^\\* DONE Foo" (test-agent-helpers--contents test-file)))))

(ert-deftest agent-helpers/set-state-returns-wrote-plist ()
  "`set-state' returns a plist announcing which file it wrote, plus state.
Agents grep `:wrote' to know which paths to re-Read before any next Edit.
Worklog interaction is covered separately; isolate by disabling it here."
  (let ((bergheim/agent-worklog-dir nil))
    (test-agent-helpers--with-file "* TODO Foo\n"
      (let ((result (bergheim/agent-org-set-state test-file "TODO Foo" "DONE")))
        (should (listp result))
        (should (equal (plist-get result :wrote)
                       (list (expand-file-name test-file))))
        (should (equal (plist-get result :state) "DONE"))
        (should (equal (plist-get result :state-from) "TODO"))
        (should (equal (plist-get result :heading) "Foo"))))))

;; ----------------------------------------------------------------------------
;; New: ambiguity detection
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/set-state-ambiguous-errors ()
  "`set-state' errors when the heading-re matches multiple headings."
  (test-agent-helpers--with-file "* TODO Dup heading\n* TODO Dup heading\n"
    (let ((err (should-error
                (bergheim/agent-org-set-state test-file "TODO Dup heading" "DONE")
                :type 'error)))
      ;; Error message should mention ambiguity/multiple matches.
      (should (string-match-p "\\(ambigu\\|multiple\\|duplicate\\)" (error-message-string err))))))

;; ----------------------------------------------------------------------------
;; New: ensure-id
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/ensure-id-adds-and-is-idempotent ()
  "`ensure-id' adds `:ID:' on first call, returns the same ID on subsequent calls,
and reports `:wrote' only when the buffer was actually modified."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (let* ((r1 (bergheim/agent-org-ensure-id test-file "TODO Foo"))
           (r2 (bergheim/agent-org-ensure-id test-file "TODO Foo"))
           (id1 (plist-get r1 :id))
           (id2 (plist-get r2 :id)))
      (should (stringp id1))
      (should (> (length id1) 0))
      (should (string= id1 id2))
      (should (equal (plist-get r1 :heading) "Foo"))
      (should (string-match-p (concat ":ID:[[:space:]]+" (regexp-quote id1))
                              (test-agent-helpers--contents test-file)))
      ;; First call modified the buffer; second was a no-op.
      (should (equal (plist-get r1 :wrote)
                     (list (expand-file-name test-file))))
      (should (equal (plist-get r2 :wrote) nil)))))

;; ----------------------------------------------------------------------------
;; New: set-state-by-id
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/set-state-by-id ()
  "`set-state-by-id' locates heading via `:ID:' property."
  (test-agent-helpers--with-file
      "* TODO Entry one\n:PROPERTIES:\n:ID: aaa-111\n:END:\n* TODO Entry two\n:PROPERTIES:\n:ID: bbb-222\n:END:\n"
    (bergheim/agent-org-set-state-by-id test-file "bbb-222" "DONE")
    (let ((contents (test-agent-helpers--contents test-file)))
      (should (string-match-p "^\\* TODO Entry one" contents))
      (should (string-match-p "^\\* DONE Entry two" contents)))))

(ert-deftest agent-helpers/set-state-by-id-unknown-errors ()
  "`set-state-by-id' errors when the ID does not exist."
  (test-agent-helpers--with-file "* TODO Foo\n:PROPERTIES:\n:ID: aaa-111\n:END:\n"
    (should-error
     (bergheim/agent-org-set-state-by-id test-file "not-a-real-id" "DONE")
     :type 'error)))

(ert-deftest agent-helpers/set-state-by-id-returns-wrote-plist ()
  "`set-state-by-id' echoes the same `:wrote' contract as `set-state'."
  (let ((bergheim/agent-worklog-dir nil))
    (test-agent-helpers--with-file
        "* TODO Entry\n:PROPERTIES:\n:ID: zzz-321\n:END:\n"
      (let ((result (bergheim/agent-org-set-state-by-id
                     test-file "zzz-321" "DONE")))
        (should (equal (plist-get result :wrote)
                       (list (expand-file-name test-file))))
        (should (equal (plist-get result :state) "DONE"))
        (should (equal (plist-get result :state-from) "TODO"))
        (should (equal (plist-get result :id) "zzz-321"))
        (should (equal (plist-get result :heading) "Entry"))))))

;; ----------------------------------------------------------------------------
;; New: add-note
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/add-note-no-state-change ()
  "`add-note' writes to LOGBOOK without changing the TODO state."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-add-note test-file "TODO Foo" "Testing note body")
    (let ((contents (test-agent-helpers--contents test-file)))
      (should (string-match-p "^\\* TODO Foo" contents))
      (should (string-match-p ":LOGBOOK:" contents))
      (should (string-match-p "Testing note body" contents)))))

(ert-deftest agent-helpers/add-note-returns-wrote-plist ()
  "`add-note' announces the file it modified plus the matched heading."
  (let ((bergheim/agent-worklog-dir nil))
    (test-agent-helpers--with-file "* TODO Foo\n"
      (let ((result (bergheim/agent-org-add-note test-file "TODO Foo" "log entry")))
        (should (equal (plist-get result :wrote)
                       (list (expand-file-name test-file))))
        (should (equal (plist-get result :heading) "Foo"))))))

(ert-deftest agent-helpers/add-tag-returns-wrote-and-empty-on-idempotent ()
  "`add-tag' reports `:wrote' on a real change and an empty list on no-op."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (let* ((r1 (bergheim/agent-org-add-tag test-file "TODO Foo" "alpha"))
           (r2 (bergheim/agent-org-add-tag test-file "TODO Foo" "alpha")))
      (should (equal (plist-get r1 :wrote)
                     (list (expand-file-name test-file))))
      (should (member "alpha" (plist-get r1 :tags)))
      (should (equal (plist-get r1 :heading) "Foo"))
      (should (equal (plist-get r2 :wrote) nil))
      (should (member "alpha" (plist-get r2 :tags))))))

(ert-deftest agent-helpers/remove-tag-returns-wrote-and-empty-on-idempotent ()
  "`remove-tag' reports `:wrote' on a real change and empty on no-op."
  (test-agent-helpers--with-file "* TODO Foo  :alpha:\n"
    (let* ((r1 (bergheim/agent-org-remove-tag test-file "TODO Foo" "alpha"))
           (r2 (bergheim/agent-org-remove-tag test-file "TODO Foo" "alpha")))
      (should (equal (plist-get r1 :wrote)
                     (list (expand-file-name test-file))))
      (should-not (member "alpha" (plist-get r1 :tags)))
      (should (equal (plist-get r2 :wrote) nil)))))

;; ----------------------------------------------------------------------------
;; New: TODO creation and read helpers
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/tag-changes-log-timestamped-line ()
  "`add-tag'/`remove-tag' append a timestamped LOGBOOK line when tags
actually change, and stay silent on idempotent calls."
  (let ((bergheim/agent-worklog-dir nil))
    (test-agent-helpers--with-file "* TODO Foo\n"
      (bergheim/agent-org-add-tag test-file "TODO Foo" "autonomous")
      (bergheim/agent-org-add-tag test-file "TODO Foo" "autonomous") ; idempotent
      (bergheim/agent-org-remove-tag test-file "TODO Foo" "autonomous")
      (let ((contents (test-agent-helpers--contents test-file)))
        (should (string-match-p
                 (concat (regexp-quote "- Tag \"+autonomous\" ")
                         "\\[[0-9]\\{4\\}-[0-9]\\{2\\}-[0-9]\\{2\\} [A-Za-z]\\{3\\} [0-9]\\{2\\}:[0-9]\\{2\\}\\]")
                 contents))
        (should (string-match-p (regexp-quote "- Tag \"-autonomous\" ") contents))
        ;; Exactly one add line: the idempotent call logged nothing.
        (should (= 1 (cl-count-if
                      (lambda (l) (string-match-p (regexp-quote "- Tag \"+autonomous\"") l))
                      (split-string contents "\n"))))))))

(ert-deftest agent-helpers/add-todo-appends-entry-with-body-tags-and-id ()
  "`add-todo' appends a top-level entry and returns its stable ID."
  (let ((bergheim/agent-worklog-dir nil))
    (test-agent-helpers--with-file "* TODO Existing\n"
      (let* ((result (bergheim/agent-org-add-todo
                      test-file "New task" "Body line" '("alpha" "beta") "NEXT"))
             (id (plist-get result :id))
             (contents (test-agent-helpers--contents test-file)))
        (should (equal (plist-get result :wrote)
                       (list (expand-file-name test-file))))
        (should (equal (plist-get result :heading) "New task"))
        (should (equal (plist-get result :state) "NEXT"))
        (should (string-match-p "^\\* NEXT New task  :alpha:beta:" contents))
        (should (string-match-p (concat ":ID:[[:space:]]+" (regexp-quote id))
                                contents))
        (should (string-match-p "Body line" contents))))))

(ert-deftest agent-helpers/add-todo-stamps-created-property ()
  "`add-todo' stamps `:CREATED:' with an inactive timestamp so agenda
tooling that filters/groups on CREATED sees agent-created entries."
  (let ((bergheim/agent-worklog-dir nil))
    (test-agent-helpers--with-file "* TODO Existing\n"
      (bergheim/agent-org-add-todo test-file "New task")
      (should (string-match-p
               ":CREATED:[[:space:]]+\\[[0-9]\\{4\\}-[0-9]\\{2\\}-[0-9]\\{2\\} [A-Za-z]\\{3\\} [0-9]\\{2\\}:[0-9]\\{2\\}\\]"
               (test-agent-helpers--contents test-file))))))

(ert-deftest agent-helpers/add-todo-invalid-input-errors-before-write ()
  "`add-todo' validates heading and tags before mutating the file."
  (test-agent-helpers--with-file "* TODO Existing\n"
    (let ((before (test-agent-helpers--contents test-file)))
      (should-error
       (bergheim/agent-org-add-todo test-file "Bad\nheading" "body")
       :type 'error)
      (should (equal (test-agent-helpers--contents test-file) before))
      (should-error
       (bergheim/agent-org-add-todo test-file "Bad tag" nil '("bad-tag!"))
       :type 'error)
      (should (equal (test-agent-helpers--contents test-file) before)))))

(ert-deftest agent-helpers/list-todos-returns-json-for-every-todo-keyword ()
  "`list-todos' returns JSON objects in file order for TODO-keyword headings."
  (test-agent-helpers--with-file
      "* TODO First  :autonomous:\n* Plain heading\n* DONE Closed\n* NEXT Later  :alpha:\n"
    (let ((items (test-agent-helpers--json-read
                  (bergheim/agent-org-list-todos test-file))))
      (should (= (length items) 3))
      (should (equal (alist-get 'state (nth 0 items)) "TODO"))
      (should (equal (alist-get 'heading (nth 0 items)) "First"))
      (should (eq (alist-get 'autonomous (nth 0 items)) t))
      (should (equal (alist-get 'state (nth 1 items)) "DONE"))
      (should-not (alist-get 'autonomous (nth 1 items)))
      (should (equal (alist-get 'tags (nth 2 items)) '("alpha"))))))

(ert-deftest agent-helpers/get-entry-returns-body-with-drawers-removed ()
  "`get-entry' returns a JSON object for a heading regexp or ID lookup."
  (test-agent-helpers--with-file
      "* TODO Read me  :alpha:\n:PROPERTIES:\n:ID: entry-1\n:CUSTOM: value\n:END:\n:LOGBOOK:\n- hidden note\n:END:\nVisible body\n"
    (let* ((by-heading (test-agent-helpers--json-read
                        (bergheim/agent-org-get-entry test-file "Read me")))
           (by-id (test-agent-helpers--json-read
                   (bergheim/agent-org-get-entry test-file "entry-1" t))))
      (should (equal (alist-get 'state by-heading) "TODO"))
      (should (equal (alist-get 'heading by-heading) "Read me"))
      (should (equal (alist-get 'tags by-heading) '("alpha")))
      (should (string-match-p "Visible body" (alist-get 'body by-heading)))
      (should-not (string-match-p "LOGBOOK" (alist-get 'body by-heading)))
      (should (equal (alist-get 'heading by-id) "Read me")))))

;; ----------------------------------------------------------------------------
;; Agent/session metadata: LOGBOOK session lines + LAST_AGENT property
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/set-state-logs-session-line ()
  "`set-state' with AGENT and SESSION-ID appends a timestamped LOGBOOK
session line and sets `:LAST_AGENT:'. Multiple sessions accumulate."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS" nil
                                  "claude/claude-fable-5 (high)" "sess-abc-123")
    (bergheim/agent-org-set-state test-file "INPROGRESS Foo" "DONE" nil
                                  "codex/gpt-5.2" "sess-def-456")
    (let ((contents (test-agent-helpers--contents test-file)))
      (should (string-match-p
               (concat (regexp-quote "- Session claude/claude-fable-5 (high) sess-abc-123 ")
                       "\\[[0-9]\\{4\\}-[0-9]\\{2\\}-[0-9]\\{2\\} [A-Za-z]\\{3\\} [0-9]\\{2\\}:[0-9]\\{2\\}\\]")
               contents))
      (should (string-match-p (regexp-quote "- Session codex/gpt-5.2 sess-def-456")
                              contents))
      ;; LAST_AGENT is last-writer-wins.
      (should (string-match-p ":LAST_AGENT:[[:space:]]+codex/gpt-5\\.2" contents))
      (should-not (string-match-p ":LAST_AGENT:[[:space:]]+claude" contents)))))

(ert-deftest agent-helpers/set-state-no-session-line-without-agent ()
  "Without AGENT, no session line and no LAST_AGENT are written."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "DONE")
    (let ((contents (test-agent-helpers--contents test-file)))
      (should-not (string-match-p "- Session" contents))
      (should-not (string-match-p ":LAST_AGENT:" contents)))))

(ert-deftest agent-helpers/set-state-session-line-without-session-id ()
  "AGENT without SESSION-ID still logs the session line, id omitted."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "DONE" nil "pi/unknown")
    (should (string-match-p "- Session pi/unknown \\["
                            (test-agent-helpers--contents test-file)))))

(ert-deftest agent-helpers/set-state-by-id-logs-session-line ()
  "`set-state-by-id' carries the same AGENT/SESSION-ID metadata."
  (test-agent-helpers--with-file
      "* TODO Entry\n:PROPERTIES:\n:ID: zzz-999\n:END:\n"
    (bergheim/agent-org-set-state-by-id test-file "zzz-999" "INPROGRESS" nil
                                        "claude/claude-fable-5 (high)" "sess-1")
    (let ((contents (test-agent-helpers--contents test-file)))
      (should (string-match-p (regexp-quote "- Session claude/claude-fable-5 (high) sess-1")
                              contents))
      (should (string-match-p ":LAST_AGENT:" contents)))))

(ert-deftest agent-helpers/set-state-never-adds-session-id ()
  "The fabricated :SESSION_ID: property is gone — never written."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS" nil
                                  "claude/claude-fable-5 (high)" "sess-abc")
    (should-not (string-match-p ":SESSION_ID:"
                                (test-agent-helpers--contents test-file)))))

;; ----------------------------------------------------------------------------
;; Unknown states
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/unknown-state-errors ()
  "A keyword the file does not declare must fail, not appear to succeed.
BLOCKED is the live example: AGENTS.md told agents to use it for years while
no keyword set defined it."
  (test-agent-helpers--with-file "* INPROGRESS Foo\n"
    (should-error (bergheim/agent-org-set-state test-file "INPROGRESS Foo" "BLOCKED"))
    (should (string-match-p "^\\* INPROGRESS Foo"
                            (test-agent-helpers--contents test-file)))))

;; ----------------------------------------------------------------------------
;; Durations: state lines, not clocks
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/no-clock-lines-written ()
  "Agents must not clock. org-clock has one marker per Emacs process, so
clocking in on one heading clocks out of another agent's file, outside the
`--with-file' that owns it, leaving that buffer unsaved and every later
helper call on it failing. org-clock is not even loaded any more."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS")
    (bergheim/agent-org-set-state test-file "INPROGRESS Foo" "DONE")
    (let ((contents (test-agent-helpers--contents test-file)))
      (should (string-match-p "^\\* DONE Foo" contents))
      (should-not (string-match-p "CLOCK:" contents)))))

(ert-deftest agent-helpers/state-lines-carry-the-interval ()
  "The span is recoverable without clocks: INPROGRESS and its exit are both
timestamped in the LOGBOOK, which is what duration reporting reads."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS")
    (bergheim/agent-org-set-state test-file "INPROGRESS Foo" "DONE")
    (let ((contents (test-agent-helpers--contents test-file)))
      (should (string-match-p "State \"INPROGRESS\".*\\[.+\\]" contents))
      (should (string-match-p "State \"DONE\".*\\[.+\\]" contents)))))

;; ----------------------------------------------------------------------------
;; Review feedback: no silent clobber of unsaved edits in an open buffer
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/errors-on-unsaved-modifications-in-existing-buffer ()
  "If FILE is already visited and the buffer has unsaved changes, the helper
must error rather than silently revert (which would drop the user's work)."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (let ((buf (find-file-noselect test-file t)))
      (unwind-protect
          (progn
            (with-current-buffer buf
              (goto-char (point-max))
              (insert "\n* TODO Pending unsaved edit\n")
              (should (buffer-modified-p)))
            (should-error
             (bergheim/agent-org-set-state test-file "TODO Foo" "DONE")
             :type 'error)
            (with-current-buffer buf
              (should (buffer-modified-p))
              (should (string-match-p "Pending unsaved edit" (buffer-string)))))
        (with-current-buffer buf (set-buffer-modified-p nil))))))

;; ----------------------------------------------------------------------------
;; Review feedback: note is always persisted, regardless of org log config
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/note-persists-even-when-state-does-not-request-logging ()
  "A NOTE passed to `set-state' lands in :LOGBOOK: even if the target state
does not request a log-note through the user's org-log configuration."
  (let ((org-log-done nil)
        (org-todo-log-states nil))
    (test-agent-helpers--with-file "* TODO Foo\n"
      ;; CANCELLED carries no logging flag, so org itself requests nothing.
      (bergheim/agent-org-set-state test-file "TODO Foo" "CANCELLED" "Because reasons")
      (let ((contents (test-agent-helpers--contents test-file)))
        (should (string-match-p "^\\* CANCELLED Foo" contents))
        (should (string-match-p ":LOGBOOK:" contents))
        (should (string-match-p "Because reasons" contents))))))

;; ----------------------------------------------------------------------------
;; Review feedback: heading-re must match heading lines only, not body text
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/body-text-does-not-cause-false-ambiguity ()
  "Body text containing the heading regex must not trigger ambiguity.
The helper matches heading lines only."
  (test-agent-helpers--with-file
      "* TODO Foo\nA paragraph referencing TODO Foo in body text.\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "DONE")
    (should (string-match-p "^\\* DONE Foo"
                            (test-agent-helpers--contents test-file)))))

;;; Notes auto-commit (public-notes mode)

(defmacro test-agent-helpers--with-notes-repo (var &rest body)
  "Create a temp project with a git-inited `docs/' subdir. Bind VAR to the
absolute path of the docs dir and execute BODY. Cleans up on exit.
Configures a minimal committer identity so tests do not depend on the
host git config."
  (declare (indent 1))
  `(let* ((project (make-temp-file "agent-notes-proj-" t))
          (,var (expand-file-name "docs" project)))
     (unwind-protect
         (progn
           (make-directory ,var)
           (let ((default-directory (file-name-as-directory ,var)))
             (call-process "git" nil nil nil "init" "-q" "-b" "main")
             (call-process "git" nil nil nil "config" "user.email" "t@example.com")
             (call-process "git" nil nil nil "config" "user.name" "Test")
             (call-process "git" nil nil nil "config" "commit.gpgsign" "false")
             (call-process "git" nil nil nil "config" "tag.gpgsign" "false")
             (call-process "git" nil nil nil "commit" "-q" "--allow-empty" "-m" "init"))
           ,@body)
       (delete-directory project t))))

(defun test-agent-helpers--git-log (dir)
  "Return the output of `git log --pretty=%s` in DIR, as a list of subjects."
  (let ((default-directory (file-name-as-directory dir)))
    (with-temp-buffer
      (call-process "git" nil t nil "log" "--pretty=%s")
      (split-string (string-trim (buffer-string)) "\n" t))))

(ert-deftest agent-helpers/notes-repo-root-finds-docs-with-git ()
  (test-agent-helpers--with-notes-repo docs-dir
    (let ((inside (expand-file-name "TODO.org" docs-dir)))
      (should (equal (file-truename docs-dir)
                     (file-truename
                      (bergheim/agent-notes--repo-root inside)))))))

(ert-deftest agent-helpers/notes-repo-root-returns-nil-without-git ()
  (let* ((project (make-temp-file "agent-notes-plain-" t))
         (docs-dir (expand-file-name "docs" project)))
    (unwind-protect
        (progn
          (make-directory docs-dir)
          (let ((inside (expand-file-name "TODO.org" docs-dir)))
            (should-not (bergheim/agent-notes--repo-root inside))))
      (delete-directory project t))))

(ert-deftest agent-helpers/notes-repo-root-ignores-non-docs-git ()
  "A `.git' in some other directory name must not trigger public-notes mode."
  (let* ((project (make-temp-file "agent-notes-other-" t))
         (other (expand-file-name "notebook" project)))
    (unwind-protect
        (progn
          (make-directory other)
          (make-directory (expand-file-name ".git" other))
          (let ((inside (expand-file-name "foo.org" other)))
            (should-not (bergheim/agent-notes--repo-root inside))))
      (delete-directory project t))))

(ert-deftest agent-helpers/maybe-commit-creates-commit ()
  (test-agent-helpers--with-notes-repo docs-dir
    (let ((f (expand-file-name "TODO.org" docs-dir)))
      (with-temp-file f (insert "* TODO Foo\n"))
      (bergheim/agent-notes--maybe-commit f "test: add TODO")
      (let ((subjects (test-agent-helpers--git-log docs-dir)))
        (should (equal (car subjects) "test: add TODO"))))))

(ert-deftest agent-helpers/maybe-commit-noop-without-repo ()
  "`maybe-commit' must be silent when `docs/.git' is absent."
  (let* ((project (make-temp-file "agent-notes-plain-" t))
         (docs-dir (expand-file-name "docs" project))
         (f (expand-file-name "TODO.org" docs-dir)))
    (unwind-protect
        (progn
          (make-directory docs-dir)
          (with-temp-file f (insert "x"))
          ;; Must not error, must not create a repo.
          (bergheim/agent-notes--maybe-commit f "noise")
          (should-not (file-directory-p (expand-file-name ".git" docs-dir))))
      (delete-directory project t))))

(ert-deftest agent-helpers/maybe-commit-noop-when-nothing-staged ()
  (test-agent-helpers--with-notes-repo docs-dir
    (let ((f (expand-file-name "TODO.org" docs-dir))
          (before-count))
      (with-temp-file f (insert "* TODO Foo\n"))
      (bergheim/agent-notes--maybe-commit f "first")
      (setq before-count (length (test-agent-helpers--git-log docs-dir)))
      ;; Second call with no changes: no new commit.
      (bergheim/agent-notes--maybe-commit f "second")
      (should (equal before-count
                     (length (test-agent-helpers--git-log docs-dir)))))))

(ert-deftest agent-helpers/set-state-commits-in-public-notes-mode ()
  "Helpers must auto-commit when the target file lives under a public-notes docs repo."
  (test-agent-helpers--with-notes-repo docs-dir
    (let* ((f (expand-file-name "TODO.org" docs-dir))
           (inhibit-message t))
      (with-temp-file f
        (insert test-agent-helpers--keyword-header)
        (insert "* TODO Foo\n"))
      (let ((default-directory (file-name-as-directory docs-dir)))
        (call-process "git" nil nil nil "add" "-A")
        (call-process "git" nil nil nil "commit" "-q" "-m" "seed"))
      (bergheim/agent-org-set-state f "TODO Foo" "DONE")
      (let ((subjects (test-agent-helpers--git-log docs-dir)))
        (should (string-match-p "^state: → DONE" (car subjects)))))))

(ert-deftest agent-helpers/set-state-does-not-commit-in-private-mode ()
  "In a plain `docs/' dir without nested `.git', helpers must not initialize a repo."
  (let* ((project (make-temp-file "agent-notes-private-" t))
         (docs-dir (expand-file-name "docs" project))
         (f (expand-file-name "TODO.org" docs-dir))
         (inhibit-message t))
    (unwind-protect
        (progn
          (make-directory docs-dir)
          (with-temp-file f
            (insert test-agent-helpers--keyword-header)
            (insert "* TODO Foo\n"))
          (bergheim/agent-org-set-state f "TODO Foo" "DONE")
          (should-not (file-directory-p (expand-file-name ".git" docs-dir))))
      (delete-directory project t))))

;; ----------------------------------------------------------------------------
;; Worklog: cross-project tape
;; ----------------------------------------------------------------------------

(defmacro test-agent-helpers--with-worklog (worklog-path-var &rest body)
  "Bind a temp dir to `bergheim/agent-worklog-dir' and the resolved
worklog file path to WORKLOG-PATH-VAR. Cleans up on exit."
  (declare (indent 1))
  `(let* ((stash (make-temp-file "agent-worklog-" t))
          (bergheim/agent-worklog-dir stash)
          (,worklog-path-var (expand-file-name "worklog.org" stash)))
     (unwind-protect (progn ,@body)
       (delete-directory stash t))))

(ert-deftest agent-helpers/worklog-appends-on-state-change ()
  "`set-state' appends an entry with TRANSITION and SOURCE link."
  (test-agent-helpers--with-worklog log-path
    (test-agent-helpers--with-file "* TODO Foo\n"
      (bergheim/agent-org-set-state test-file "TODO Foo" "DONE")
      (let ((contents (test-agent-helpers--contents log-path)))
        (should (string-match-p "DONE  Foo" contents))
        (should (string-match-p ":TRANSITION: TODO → DONE" contents))
        (should (string-match-p ":SOURCE:.*::\\*Foo" contents))))))

(ert-deftest agent-helpers/worklog-appends-on-add-note ()
  "`add-note' appends with TRANSITION = NOTE and the note body."
  (test-agent-helpers--with-worklog log-path
    (test-agent-helpers--with-file "* TODO Foo\n"
      (bergheim/agent-org-add-note test-file "TODO Foo" "made progress")
      (let ((contents (test-agent-helpers--contents log-path)))
        (should (string-match-p "NOTE  Foo" contents))
        (should (string-match-p ":TRANSITION: NOTE" contents))
        (should (string-match-p "made progress" contents))))))

(ert-deftest agent-helpers/worklog-noop-when-dir-unset ()
  "`worklog-append' must not error or create a file when dir is nil."
  (let ((bergheim/agent-worklog-dir nil))
    (test-agent-helpers--with-file "* TODO Foo\n"
      ;; Should not error, should not create any file.
      (bergheim/agent-org-set-state test-file "TODO Foo" "DONE"))))

(ert-deftest agent-helpers/wrote-includes-worklog-when-appended ()
  "When worklog-append fires, the helper's `:wrote' includes the worklog
path so agents re-Read it before any subsequent Edit."
  (test-agent-helpers--with-worklog log-path
    (test-agent-helpers--with-file "* TODO Foo\n"
      (let* ((result (bergheim/agent-org-set-state test-file "TODO Foo" "DONE"))
             (wrote (plist-get result :wrote)))
        (should (member (expand-file-name test-file) wrote))
        (should (member log-path wrote))))))

(ert-deftest agent-helpers/plist-strings-have-no-text-properties ()
  "Plist string values must be plain strings (no font-lock properties).
Org's `org-get-heading' / `org-get-todo-state' return propertized
strings; we strip them so stdout from `emacsclient -e' is clean and
non-elisp parsers don't choke on the `#(\"...\" 0 N (...))' syntax."
  (let ((bergheim/agent-worklog-dir nil))
    (test-agent-helpers--with-file "* TODO Probe  :alpha:\n"
      (let ((r-state (bergheim/agent-org-set-state
                      test-file "TODO Probe" "DONE")))
        (should-not (text-properties-at 0 (plist-get r-state :state)))
        (should-not (text-properties-at 0 (plist-get r-state :state-from)))
        (should-not (text-properties-at 0 (plist-get r-state :heading))))))
  (let ((bergheim/agent-worklog-dir nil))
    (test-agent-helpers--with-file "* TODO Probe\n"
      (let ((r-id (bergheim/agent-org-ensure-id test-file "TODO Probe")))
        (should-not (text-properties-at 0 (plist-get r-id :id)))
        (should-not (text-properties-at 0 (plist-get r-id :heading)))))
    (test-agent-helpers--with-file "* TODO Probe\n"
      (let ((r-tag (bergheim/agent-org-add-tag test-file "TODO Probe" "x")))
        (dolist (tag (plist-get r-tag :tags))
          (should-not (text-properties-at 0 tag)))))))

(ert-deftest agent-helpers/wrote-omits-worklog-when-dir-unset ()
  "When `bergheim/agent-worklog-dir' is nil, no worklog write happens
and `:wrote' contains only the org file (or is empty on no-op)."
  (let ((bergheim/agent-worklog-dir nil))
    (test-agent-helpers--with-file "* TODO Foo\n"
      (let* ((result (bergheim/agent-org-set-state test-file "TODO Foo" "DONE"))
             (wrote (plist-get result :wrote)))
        (should (equal wrote (list (expand-file-name test-file))))))))

(ert-deftest agent-helpers/worklog-multiple-transitions-accumulate ()
  "Subsequent helper calls append to the same worklog file."
  (test-agent-helpers--with-worklog log-path
    (test-agent-helpers--with-file "* TODO Foo\n* TODO Bar\n"
      (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS")
      (bergheim/agent-org-set-state test-file "TODO Bar" "DONE")
      (let ((contents (test-agent-helpers--contents log-path)))
        (should (string-match-p "INPROGRESS  Foo" contents))
        (should (string-match-p "DONE  Bar" contents))))))

(ert-deftest agent-helpers/worklog-recent-returns-json-tail ()
  "`worklog-recent' returns the last N entries as JSON."
  (test-agent-helpers--with-worklog log-path
    (test-agent-helpers--with-file "* TODO Foo\n* TODO Bar\n"
      (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS")
      (bergheim/agent-org-set-state test-file "TODO Bar" "DONE")
      (let ((items (test-agent-helpers--json-read
                    (bergheim/agent-worklog-recent 1))))
        (should (= (length items) 1))
        (should (equal (alist-get 'project (car items))
                       (bergheim/agent-worklog--project-name test-file)))
        (should (equal (alist-get 'transition (car items)) "TODO → DONE"))
        (should (string-match-p "DONE  Bar" (alist-get 'summary (car items))))))))

(ert-deftest agent-helpers/worklog-recent-empty-when-unconfigured ()
  "`worklog-recent' returns an empty JSON array without a worklog file."
  (let ((bergheim/agent-worklog-dir nil))
    (should (equal (test-agent-helpers--json-read
                    (bergheim/agent-worklog-recent 5))
                   '()))))

;; ----------------------------------------------------------------------------
;; Denote helpers: structured returns
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/denote-create-returns-wrote-plist ()
  "`denote-create' returns a plist with :wrote, :path, :id, :title."
  (let ((dir (make-temp-file "agent-denote-" t)))
    (unwind-protect
        (let ((result (bergheim/agent-denote-create
                       dir "Hello world" '("kind" "topic"))))
          (should (equal (plist-get result :wrote)
                         (list (plist-get result :path))))
          (should (file-exists-p (plist-get result :path)))
          (should (string-match-p "[0-9]\\{8\\}T[0-9]\\{6\\}"
                                  (plist-get result :id)))
          (should (equal (plist-get result :title) "Hello world")))
      (delete-directory dir t))))

(ert-deftest agent-helpers/denote-list-returns-index-without-path ()
  "`denote-list' is an index view; `denote-find' carries paths."
  (let ((dir (make-temp-file "agent-denote-" t)))
    (unwind-protect
        (let* ((created (bergheim/agent-denote-create
                         dir "Indexed note" '("kind" "topic")))
               (listed (car (bergheim/agent-denote-list dir 1)))
               (found (car (bergheim/agent-denote-find dir '("kind") "Indexed"))))
          (should (equal (plist-get listed :id) (plist-get created :id)))
          (should (equal (plist-get listed :title) "indexed note"))
          (should (equal (plist-get listed :keywords) '("kind" "topic")))
          (should-not (plist-member listed :path))
          (should (equal (plist-get found :path) (plist-get created :path))))
      (delete-directory dir t))))

(ert-deftest agent-helpers/denote-get-backlinks-finds-linking-notes ()
  "`denote-get-backlinks' reports notes that link to the target path."
  (skip-unless (require 'denote nil t))
  (let ((dir (make-temp-file "agent-denote-" t)))
    (unwind-protect
        (let* ((source (bergheim/agent-denote-create
                        dir "Source note" '("kind" "source")))
               (target (bergheim/agent-denote-create
                        dir "Target note" '("kind" "target")))
               (source-path (plist-get source :path))
               (target-path (plist-get target :path)))
          (bergheim/agent-denote-link source-path (list target-path))
          (let ((backlinks (bergheim/agent-denote-get-backlinks target-path)))
            (should (= (length backlinks) 1))
            (should (equal (plist-get (car backlinks) :path) source-path))
            (should (equal (plist-get (car backlinks) :title) "Source note"))))
      (dolist (buf (buffer-list))
        (let ((path (buffer-file-name buf)))
          (when (and path
                     (string-prefix-p (file-truename dir)
                                      (file-truename path)))
            (with-current-buffer buf
              (set-buffer-modified-p nil))
            (kill-buffer buf))))
      (delete-directory dir t))))

(ert-deftest agent-helpers/with-file-reverts-stale-visiting-buffer-without-prompt ()
  "Disk change under a live visiting buffer must not call read-event."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (find-file-noselect test-file t)
    (with-temp-file test-file
      (insert test-agent-helpers--keyword-header)
      (insert "* TODO Foo\n"))
    (let ((prompted nil))
      (cl-letf (((symbol-function 'read-event)
                 (lambda (&rest _)
                   (setq prompted t)
                   ?n)))
        (bergheim/agent-org-add-note test-file "Foo" "from agent"))
      (should-not prompted)
      (should (string-match-p "from agent"
                              (test-agent-helpers--contents test-file))))))

(ert-deftest agent-helpers/noninteractive-errors-instead-of-prompting ()
  "A prompt we did not anticipate must signal, not hold the daemon."
  (should-error (bergheim/agent--noninteractive (read-string "who? "))
                :type 'inhibited-interaction)
  (should-error (bergheim/agent--noninteractive (y-or-n-p "really? "))
                :type 'inhibited-interaction))

(ert-deftest agent-helpers/noninteractive-does-not-leak-to-interactive-emacs ()
  "The guard is scoped to the agent call; the user keeps their prompts."
  (should-not inhibit-interaction)
  (should (bergheim/agent--noninteractive inhibit-interaction))
  (should-not inhibit-interaction))

(ert-deftest agent-helpers/stale-buffer-with-unsaved-edits-errors ()
  "Unsaved edits under a changed file: error loudly, never prompt or clobber."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (with-current-buffer (find-file-noselect test-file t)
      (goto-char (point-max))
      (insert "* TODO Unsaved human edit\n"))
    (with-temp-file test-file
      (insert test-agent-helpers--keyword-header)
      (insert "* TODO Foo\nchanged on disk\n"))
    (let ((prompted nil))
      (cl-letf (((symbol-function 'read-event)
                 (lambda (&rest _) (setq prompted t) ?n)))
        (should-error (bergheim/agent-org-add-note test-file "Foo" "from agent")))
      (should-not prompted)
      (should (string-match-p "changed on disk"
                              (test-agent-helpers--contents test-file))))))

(provide 'test-agent-helpers)
;;; test-agent-helpers.el ends here
