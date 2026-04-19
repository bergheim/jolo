;;; bergheim-agent-helpers.el --- Agent helpers for org-mode and denote -*- lexical-binding: t; -*-

(require 'cl-lib)
(require 'json)
(require 'org)

(defun bergheim/agent-org-set-state (file heading-re new-state &optional note)
  "Transition the first TODO matching HEADING-RE in FILE to NEW-STATE.
Safe to call from `emacsclient --eval' — never prompts interactively."
  (with-current-buffer (find-file-noselect file t)
    (let ((auto-revert-mode nil)
          (super-save-mode nil))
      (revert-buffer t t)
      (goto-char (point-min))
      (unless (re-search-forward heading-re nil t)
        (error "Heading not found: %s" heading-re))
      (org-back-to-heading t)
      (let ((old-state (org-get-todo-state)))
        (org-todo new-state)
        (let ((actual-state (org-get-todo-state)))
          (unless (equal actual-state new-state)
            (error "State change blocked: %s -> %s (got %s)"
                   old-state new-state actual-state))
          (when (memq 'org-add-log-note (default-value 'post-command-hook))
            (remove-hook 'post-command-hook 'org-add-log-note)
            (org-add-log-note))
          (when (get-buffer "*Org Note*")
            (with-current-buffer "*Org Note*"
              (goto-char (point-max))
              (when note (insert note))
              (org-store-log-note)))
          (save-buffer)))))
  t)

;;; Denote-compatible agent helpers
;; Create/find/list/read follow denote's filename convention without requiring
;; denote.el. Linking requires denote.el for proper [[denote:ID]] links.

(defun bergheim/agent-denote--slugify (title)
  "Convert TITLE to a denote-compatible filename slug."
  (let* ((s (downcase title))
         (s (replace-regexp-in-string "[^a-z0-9 -]" "" s))
         (s (string-trim s))
         (s (replace-regexp-in-string " +" "-" s))
         (s (replace-regexp-in-string "-\\{2,\\}" "-" s)))
    s))

(defun bergheim/agent-denote--sanitize-keyword (kw)
  "Sanitize KW for use in denote filenames and filetags.
Replaces underscores and spaces with hyphens, strips non-alphanumeric chars."
  (let* ((s (downcase kw))
         (s (replace-regexp-in-string "[_ ]" "-" s))
         (s (replace-regexp-in-string "[^a-z0-9-]" "" s))
         (s (replace-regexp-in-string "-\\{2,\\}" "-" s))
         (s (replace-regexp-in-string "^-\\|-$" "" s)))
    s))

(defun bergheim/agent-denote--parse-filename (filepath)
  "Parse a denote-format FILEPATH into plist with :id :title :keywords :path.
Returns nil if the filename doesn't match denote format."
  (let ((name (file-name-sans-extension (file-name-nondirectory filepath))))
    (when (string-match "\\`\\([0-9]\\{8\\}T[0-9]\\{6\\}\\(?:-[0-9]+\\)?\\)--\\([^_]+\\)\\(?:__\\(.+\\)\\)?\\'" name)
      (list :id (match-string 1 name)
            :title (replace-regexp-in-string "-" " " (match-string 2 name))
            :keywords (when (match-string 3 name)
                        (split-string (match-string 3 name) "_"))
            :path filepath))))

(defun bergheim/agent-denote-create (dir title keywords &optional body)
  "Create a denote-format note in DIR with TITLE, KEYWORDS list, and BODY.
KEYWORDS are sanitized (underscores/spaces become hyphens).
On same-second collision, appends a counter suffix to the ID.
Returns the absolute file path. Safe for emacsclient --eval."
  (let* ((id (format-time-string "%Y%m%dT%H%M%S"))
         (slug (bergheim/agent-denote--slugify title))
         (clean-kw (seq-filter (lambda (s) (not (string-empty-p s)))
                               (mapcar #'bergheim/agent-denote--sanitize-keyword keywords)))
         (kw-part (if clean-kw (concat "__" (mapconcat #'identity clean-kw "_")) ""))
         (dir (expand-file-name dir))
         (date-str (format-time-string "[%Y-%m-%d %a %H:%M]"))
         (tags-str (if clean-kw
                       (concat ":" (mapconcat #'identity clean-kw ":") ":")
                     ""))
         filepath filename final-id)
    (when (string-empty-p slug)
      (setq slug "untitled"))
    (unless (file-directory-p dir)
      (make-directory dir t))
    (setq final-id id
          filename (concat final-id "--" slug kw-part ".org")
          filepath (expand-file-name filename dir))
    (let ((counter 0)
          (content (concat (format "#+title:      %s\n" title)
                           (format "#+date:       %s\n" date-str)
                           (format "#+filetags:   %s\n" tags-str)
                           (format "#+identifier: %s\n" id)
                           "\n"
                           (if body (concat body "\n") "")))
          (written nil))
      (while (not written)
        (condition-case nil
            (progn
              (write-region content nil filepath nil nil nil 'excl)
              (setq written t))
          (file-already-exists
           (setq counter (1+ counter)
                 final-id (format "%s-%d" id counter)
                 filename (concat final-id "--" slug kw-part ".org")
                 filepath (expand-file-name filename dir)
                 content (replace-regexp-in-string
                          "^#\\+identifier:.*$"
                          (format "#+identifier: %s" final-id)
                          content)))))
      filepath)))

(defun bergheim/agent-denote-find (dir &optional keywords title-re)
  "Find denote notes in DIR, optionally filtered by KEYWORDS and TITLE-RE.
KEYWORDS is a list of strings; a note matches if it has ALL of them.
TITLE-RE is a regexp matched against the title (spaces, not hyphens).
Returns list of plists (:id :title :keywords :path) sorted newest first."
  (let* ((dir (expand-file-name dir))
         (files (and (file-directory-p dir)
                     (directory-files dir t "\\`[0-9]\\{8\\}T[0-9]\\{6\\}\\(-[0-9]+\\)?--.*\\.org\\'" t)))
         (parsed (delq nil (mapcar #'bergheim/agent-denote--parse-filename files)))
         (filtered
          (seq-filter
           (lambda (note)
             (and (or (null keywords)
                      (let ((nk (plist-get note :keywords)))
                        (seq-every-p (lambda (k) (member k nk)) keywords)))
                  (or (null title-re)
                      (string-match-p title-re (plist-get note :title)))))
           parsed)))
    (sort filtered (lambda (a b)
                     (string> (plist-get a :id) (plist-get b :id))))))

(defun bergheim/agent-denote-read (filepath)
  "Read denote note at FILEPATH. Returns content as string."
  (unless (file-exists-p filepath)
    (error "Note not found: %s" filepath))
  (with-temp-buffer
    (insert-file-contents filepath)
    (buffer-string)))

(defun bergheim/agent-denote-list (dir &optional limit)
  "List denote notes in DIR, newest first. Returns up to LIMIT entries (default 10).
Each entry is a plist with :id :title :keywords :path."
  (let* ((all (bergheim/agent-denote-find dir))
         (n (or limit 10)))
    (seq-take all n)))

(defun bergheim/agent-denote-link (source-path target-paths)
  "Add denote links from SOURCE-PATH to each file in TARGET-PATHS.
Appends a \"Related notes\" section if absent, then adds any links not
already present. Uses denote.el APIs for proper [[denote:ID]] links.
TARGET-PATHS is a list of absolute paths to denote notes.
Safe for emacsclient --eval."
  (require 'denote)
  (let ((denote-directory (file-name-directory source-path))
        (source-buf (find-file-noselect source-path t)))
    (with-current-buffer source-buf
      (let ((auto-revert-mode nil)
            (super-save-mode nil))
        (revert-buffer t t)
        (let ((links-to-add
               (delq nil
                     (mapcar
                      (lambda (target)
                        (let* ((id (denote-retrieve-filename-identifier target))
                               (title (denote-retrieve-front-matter-title-value target 'org))
                               (link (denote-format-link target title 'org nil)))
                          (save-excursion
                            (goto-char (point-min))
                            (unless (search-forward (concat "denote:" id) nil t)
                              link))))
                      target-paths))))
          (when links-to-add
            (goto-char (point-min))
            (if (re-search-forward "^\\* Related notes" nil t)
                (progn
                  (if (re-search-forward "^\\*" nil t)
                      (forward-line -1)
                    (goto-char (point-max)))
                  (unless (bolp) (insert "\n")))
              (goto-char (point-max))
              (unless (bolp) (insert "\n"))
              (insert "\n* Related notes\n"))
            (dolist (link links-to-add)
              (insert "- " link "\n"))
            (save-buffer))
          (length links-to-add))))))

;;; Autonomous dispatch selector/marker
;; Companion to `jolo autonomous'. Safe for `emacsclient --eval' — never
;; prompts, refreshes stale buffers when possible, and marks by opaque
;; buffer position instead of heading text.
;;
;;   (bergheim/agent-org-autonomous-select ORG-FILE)
;;     Returns a JSON array string. Each element is an object with
;;       position — buffer (point) of the heading, used as stable identity
;;       heading  — title with TODO keyword / tags / priority stripped
;;       body     — entry body, all drawers removed
;;     Items are selected when all of the following hold:
;;       - todo state is TODO, NEXT, or INPROGRESS
;;       - tags include :autonomous:
;;       - no :DISPATCHED: property (idempotency guard)
;;
;;   (bergheim/agent-org-autonomous-mark-dispatched ORG-FILE POSITION TS)
;;     Sets :DISPATCHED: TS on the entry at POSITION. POSITION is the
;;     opaque buffer offset returned by -select above. Returns non-nil
;;     on success, nil if the entry is no longer eligible.

(defconst bergheim/agent-org--autonomous-dispatchable-states
  '("TODO" "NEXT" "INPROGRESS"))

(defmacro bergheim/agent-org--with-quiet-buffer (abs-file &rest body)
  "Visit ABS-FILE and run BODY without interactive prompts.

Suppresses the \"File is read-only on disk; make buffer read-only too?\"
prompt from `find-file-noselect-1', plus any other y/n or yes/no prompts
that would block an autonomous call.

Also reverts the buffer from disk when safe (unmodified + stale modtime):
if the host daemon already had this org file open from an earlier session,
selection must reflect edits made outside Emacs (git checkout, other
tooling) and marks must not save stale contents back over newer work."
  (declare (indent 1))
  `(cl-letf (((symbol-function 'y-or-n-p) #'ignore)
             ((symbol-function 'yes-or-no-p) #'ignore))
     (let ((inhibit-message t)
           (find-file-suppress-same-file-warnings t))
       (with-current-buffer (find-file-noselect ,abs-file)
         (when (and (not (buffer-modified-p))
                    (not (verify-visited-file-modtime)))
           (revert-buffer t t t))
         (let ((inhibit-read-only t))
           ,@body)))))

(defconst bergheim/agent-org--drawer-regexp
  "^[[:space:]]*:[A-Za-z][A-Za-z_-]*:[[:space:]]*\n\\(?:.\\|\n\\)*?^[[:space:]]*:END:[[:space:]]*$"
  "Match any :NAME: ... :END: drawer (including LOGBOOK and custom drawers).")

(defun bergheim/agent-org--autonomous-body ()
  "Body of the entry at point with all drawers removed."
  (save-excursion
    (org-back-to-heading t)
    (let ((start (progn (org-end-of-meta-data t) (point)))
          (end (or (save-excursion (outline-next-heading) (point))
                   (point-max))))
      (string-trim
       (replace-regexp-in-string
        bergheim/agent-org--drawer-regexp ""
        (buffer-substring-no-properties start end))))))

(defun bergheim/agent-org--autonomous-eligible-p ()
  "Non-nil if the entry at point is eligible for autonomous dispatch."
  (and (not (org-entry-get nil "DISPATCHED"))
       (member (org-get-todo-state)
               bergheim/agent-org--autonomous-dispatchable-states)))

(defun bergheim/agent-org-autonomous-select (org-file)
  "Return JSON array of :autonomous: entries without :DISPATCHED: in ORG-FILE.

Each element has three fields: `position' (buffer character offset of the
heading, used as a stable identifier for marking), `heading' (stripped
heading text), and `body' (body with drawers removed)."
  (let ((abs (expand-file-name org-file))
        (items nil))
    (bergheim/agent-org--with-quiet-buffer abs
      (org-with-wide-buffer
       (org-map-entries
        (lambda ()
          (when (and (member "autonomous" (org-get-tags))
                     (bergheim/agent-org--autonomous-eligible-p))
            (push `((position . ,(point))
                    (heading . ,(substring-no-properties
                                 (org-get-heading t t t t)))
                    (body . ,(bergheim/agent-org--autonomous-body)))
                  items)))
        nil nil)))
    ;; `json-encode' on nil returns "null"; force array encoding so the empty
    ;; case round-trips as JSON "[]".
    (json-encode-array (nreverse items))))

(defun bergheim/agent-org-autonomous-mark-dispatched (org-file position timestamp)
  "Set :DISPATCHED: TIMESTAMP on the entry at POSITION in ORG-FILE.

POSITION is the `(point)' value returned by `-select'. Using the buffer
position instead of heading text avoids mis-marking duplicate-titled
entries. Returns non-nil if the mark was applied, nil if the entry at
POSITION is no longer `:autonomous:' or is no longer eligible."
  (let ((abs (expand-file-name org-file))
        (marked nil))
    (bergheim/agent-org--with-quiet-buffer abs
      (org-with-wide-buffer
       (goto-char position)
       (when (and (ignore-errors (org-back-to-heading t) t)
                  (member "autonomous" (org-get-tags))
                  (bergheim/agent-org--autonomous-eligible-p))
         (org-entry-put nil "DISPATCHED" timestamp)
         (setq marked t)))
      (when marked (save-buffer)))
    marked))

(provide 'bergheim-agent-helpers)
;;; bergheim-agent-helpers.el ends here
