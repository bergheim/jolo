;;; emacs-autonomous.el --- Selector for :autonomous: org items  -*- lexical-binding: t; -*-

;; Companion to `jolo autonomous'. Load this file in the Emacs daemon
;; that `emacsclient' talks to (host-side, not inside a devcontainer)
;; so the CLI can query and mutate org state:
;;
;;   (load "/path/to/emacs-container/container/emacs-autonomous.el")
;;
;; Exposed functions:
;;
;;   (bergheim/agent-org-autonomous-select ORG-FILE)
;;     Returns a JSON array string. Each element is an object with
;;       heading — title with TODO keyword / tags / priority stripped
;;       body    — entry body, property and logbook drawers removed
;;     Items are selected when all of the following hold:
;;       - todo state is TODO, NEXT, or INPROGRESS
;;       - tags include :autonomous:
;;       - no :DISPATCHED: property (idempotency guard)
;;
;;   (bergheim/agent-org-autonomous-mark-dispatched ORG-FILE HEADING TS)
;;     Sets :DISPATCHED: TS on the heading matching HEADING (stripped
;;     form from -select above) and saves the buffer.

(require 'cl-lib)
(require 'json)
(require 'org)

(defconst bergheim/agent-org--autonomous-dispatchable-states
  '("TODO" "NEXT" "INPROGRESS"))

(defmacro bergheim/agent-org--with-quiet-buffer (abs-file &rest body)
  "Visit ABS-FILE and run BODY without interactive prompts.

Suppresses the \"File is read-only on disk; make buffer read-only too?\"
prompt from `find-file-noselect-1', plus any other y/n or yes/no prompts
that would block an autonomous call."
  (declare (indent 1))
  `(cl-letf (((symbol-function 'y-or-n-p) #'ignore)
             ((symbol-function 'yes-or-no-p) #'ignore))
     (let ((inhibit-message t)
           (find-file-suppress-same-file-warnings t))
       (with-current-buffer (find-file-noselect ,abs-file)
         (let ((inhibit-read-only t))
           ,@body)))))

(defun bergheim/agent-org--autonomous-body ()
  "Body of the entry at point with property and logbook drawers removed."
  (save-excursion
    (org-back-to-heading t)
    (let ((start (progn (org-end-of-meta-data t) (point)))
          (end (or (save-excursion (outline-next-heading) (point))
                   (point-max))))
      (string-trim (buffer-substring-no-properties start end)))))

(defun bergheim/agent-org-autonomous-select (org-file)
  "Return JSON array of :autonomous: entries without :DISPATCHED: in ORG-FILE."
  (let ((abs (expand-file-name org-file))
        (items nil))
    (bergheim/agent-org--with-quiet-buffer abs
      (org-with-wide-buffer
       (org-map-entries
        (lambda ()
          (when (and (member "autonomous" (org-get-tags))
                     (not (org-entry-get nil "DISPATCHED"))
                     (member (org-get-todo-state)
                             bergheim/agent-org--autonomous-dispatchable-states))
            (push `((heading . ,(substring-no-properties
                                 (org-get-heading t t t t)))
                    (body . ,(bergheim/agent-org--autonomous-body)))
                  items)))
        nil nil)))
    ;; `json-encode' on nil returns "null"; force array encoding so the empty
    ;; case round-trips as JSON "[]".
    (json-encode-array (nreverse items))))

(defun bergheim/agent-org-autonomous-mark-dispatched (org-file heading timestamp)
  "Set :DISPATCHED: TIMESTAMP on the :autonomous: entry matching HEADING.

Only entries tagged :autonomous: and not already carrying :DISPATCHED:
are considered, so a heading that collides with body text elsewhere
cannot be mis-marked, and repeated dispatches of same-named items are
applied to a distinct entry on each run."
  (let ((abs (expand-file-name org-file))
        (marked nil))
    (bergheim/agent-org--with-quiet-buffer abs
      (org-with-wide-buffer
       (org-map-entries
        (lambda ()
          (when (and (not marked)
                     (not (org-entry-get nil "DISPATCHED"))
                     (string= heading
                              (substring-no-properties
                               (org-get-heading t t t t))))
            (org-entry-put nil "DISPATCHED" timestamp)
            (setq marked t)))
        "+autonomous" nil))
      (when marked (save-buffer)))
    marked))

(provide 'emacs-autonomous)

;;; emacs-autonomous.el ends here
