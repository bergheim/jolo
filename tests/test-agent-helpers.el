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

(provide 'test-agent-helpers)
;;; test-agent-helpers.el ends here
