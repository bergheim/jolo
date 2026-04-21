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

(defvar test-agent-helpers--keyword-header
  "#+TODO: TODO(t) NEXT(n) INPROGRESS(i) WAITING(w) BLOCKED(b) | DONE(d) CANCELLED(c)\n\n"
  "TODO keyword declaration used by test fixtures.")

(defmacro test-agent-helpers--with-file (body-string &rest body)
  "Create a temp org file containing BODY-STRING (prefixed with the keyword
header), bind its path to `test-file', clock out any running clock, and
kill the buffer afterward."
  (declare (indent 1))
  `(let* ((test-file (make-temp-file "agent-helpers-test-" nil ".org"))
          (inhibit-message t))
     (unwind-protect
         (progn
           (with-temp-file test-file
             (insert test-agent-helpers--keyword-header)
             (insert ,body-string))
           ,@body)
       ;; Clock-in/out tests may leave an active clock — close it so the
       ;; buffer-kill below does not trigger org's "Save clock?" machinery
       ;; which prompts on stdin and errors out in batch mode.
       (when (and (fboundp 'org-clocking-p) (org-clocking-p))
         (ignore-errors (org-clock-out nil t)))
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

;; ----------------------------------------------------------------------------
;; Existing set-state behavior (should keep passing)
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/set-state-basic ()
  "`set-state' transitions TODO to DONE."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "DONE")
    (should (string-match-p "^\\* DONE Foo" (test-agent-helpers--contents test-file)))))

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
  "`ensure-id' adds `:ID:' property and returns the same ID on subsequent calls."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (let* ((id1 (bergheim/agent-org-ensure-id test-file "TODO Foo"))
           (id2 (bergheim/agent-org-ensure-id test-file "TODO Foo")))
      (should (stringp id1))
      (should (> (length id1) 0))
      (should (string= id1 id2))
      (should (string-match-p (concat ":ID:[[:space:]]+" (regexp-quote id1))
                              (test-agent-helpers--contents test-file))))))

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

;; ----------------------------------------------------------------------------
;; New: SESSION_ID auto-assignment on INPROGRESS
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/session-id-auto-assign-on-inprogress ()
  "`set-state' with ensure-session-id adds `:SESSION_ID:' on INPROGRESS transition."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS" nil t)
    (let ((contents (test-agent-helpers--contents test-file)))
      (should (string-match-p "^\\* INPROGRESS Foo" contents))
      (should (string-match-p ":SESSION_ID:" contents)))))

(ert-deftest agent-helpers/session-id-not-added-on-done ()
  "`set-state' with ensure-session-id does NOT add SESSION_ID on DONE transition."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "DONE" nil t)
    (let ((contents (test-agent-helpers--contents test-file)))
      (should-not (string-match-p ":SESSION_ID:" contents)))))

;; ----------------------------------------------------------------------------
;; New: BLOCKED state
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/blocked-transition ()
  "Transition to BLOCKED works (keyword recognized via #+TODO: header)."
  (test-agent-helpers--with-file "* INPROGRESS Foo\n"
    (bergheim/agent-org-set-state test-file "INPROGRESS Foo" "BLOCKED")
    (should (string-match-p "^\\* BLOCKED Foo"
                            (test-agent-helpers--contents test-file)))))

;; ----------------------------------------------------------------------------
;; New: clock integration
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/clock-in-on-inprogress ()
  "`set-state' with CLOCK starts an org-clock when transitioning to INPROGRESS."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS" nil nil t)
    (let ((contents (test-agent-helpers--contents test-file)))
      (should (string-match-p "^\\* INPROGRESS Foo" contents))
      (should (string-match-p ":LOGBOOK:" contents))
      (should (string-match-p "CLOCK:" contents)))))

(ert-deftest agent-helpers/clock-out-on-done ()
  "`set-state' with CLOCK closes an open clock when transitioning to DONE."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS" nil nil t)
    (bergheim/agent-org-set-state test-file "INPROGRESS Foo" "DONE" nil nil t)
    (let ((contents (test-agent-helpers--contents test-file)))
      (should (string-match-p "^\\* DONE Foo" contents))
      ;; A closed clock line has the form `CLOCK: [...]--[...] => H:MM'.
      (should (string-match-p "CLOCK:.*=>" contents)))))

(ert-deftest agent-helpers/no-clock-when-disabled ()
  "Without CLOCK arg, no clock entries are produced."
  (test-agent-helpers--with-file "* TODO Foo\n"
    (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS")
    (should-not (string-match-p "CLOCK:"
                                (test-agent-helpers--contents test-file)))))

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
      (bergheim/agent-org-set-state test-file "TODO Foo" "DONE" "Because reasons")
      (let ((contents (test-agent-helpers--contents test-file)))
        (should (string-match-p "^\\* DONE Foo" contents))
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

;; ----------------------------------------------------------------------------
;; Review feedback: clock-out must target this heading, not any active clock
;; ----------------------------------------------------------------------------

(ert-deftest agent-helpers/clock-out-leaves-clock-on-other-heading-alone ()
  "Transitioning heading A to DONE with :clock must not stop a clock running
on heading B."
  (test-agent-helpers--with-file
      "* TODO Foo\n* TODO Bar\n"
    ;; Start a clock on Foo.
    (bergheim/agent-org-set-state test-file "TODO Foo" "INPROGRESS" nil nil t)
    ;; Transition Bar to DONE with :clock. Foo's clock should survive.
    (bergheim/agent-org-set-state test-file "TODO Bar" "DONE" nil nil t)
    (should (org-clocking-p))
    ;; The clock line on Foo must still be open (no `=>' duration yet).
    (let ((contents (test-agent-helpers--contents test-file)))
      (should (string-match-p
               "\\* INPROGRESS Foo\\(.\\|\n\\)*CLOCK: \\[[^]]+\\]\\s-*$"
               contents)))))

(provide 'test-agent-helpers)
;;; test-agent-helpers.el ends here
