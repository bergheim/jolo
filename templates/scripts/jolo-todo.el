;;; jolo-todo.el --- docs/TODO.org workflow automation -*- lexical-binding: t; -*-

(require 'org)
(require 'org-clock)
(require 'org-id)
(require 'subr-x)

(defgroup jolo-todo nil
  "Workflow automation for docs/TODO.org."
  :group 'org)

(defcustom jolo-todo-repo-root nil
  "Absolute repo root. Nil means detect from current directory."
  :type '(choice (const :tag "Auto-detect" nil) directory))

(defcustom jolo-todo-worktree-dir nil
  "Parent directory used for auto-created worktrees.
Nil means auto-detect: use /workspaces when writable, else <repo>/worktrees."
  :type '(choice (const :tag "Auto-detect" nil) directory))

(defcustom jolo-todo-keyword-sequence
  '("TODO(t)" "NEXT(n)" "INPROGRESS(i)" "BLOCKED(b)" "|" "DONE(d)")
  "TODO keyword sequence for docs/TODO.org."
  :type '(repeat string))

(defun jolo-todo--repo-root (&optional path)
  (expand-file-name
   (or jolo-todo-repo-root
       (locate-dominating-file (or path default-directory) ".git")
       default-directory)))

(defun jolo-todo--todo-file (&optional path)
  (expand-file-name "docs/TODO.org" (jolo-todo--repo-root path)))

(defun jolo-todo--target-buffer-p (&optional buffer)
  (with-current-buffer (or buffer (current-buffer))
    (and buffer-file-name
         (file-exists-p (jolo-todo--todo-file buffer-file-name))
         (string=
          (file-truename buffer-file-name)
          (file-truename (jolo-todo--todo-file buffer-file-name))))))

(defun jolo-todo--ensure-keywords ()
  (when (jolo-todo--target-buffer-p)
    (setq-local org-todo-keywords (list jolo-todo-keyword-sequence))))

(defun jolo-todo--slugify (text)
  (let* ((slug (downcase (replace-regexp-in-string
                          "[^[:alnum:]]+" "-"
                          (string-trim (or text "")))))
         (slug (replace-regexp-in-string "^-+" "" slug))
         (slug (replace-regexp-in-string "-+$" "" slug)))
    (if (string-empty-p slug) "task" slug)))

(defun jolo-todo--new-session-id ()
  (format "%s-%06x"
          (format-time-string "%Y%m%dT%H%M%SZ" (current-time) t)
          (random #xFFFFFF)))

(defun jolo-todo--directory-writable-p (dir)
  (let ((abs (expand-file-name dir)))
    (or (and (file-directory-p abs)
             (file-writable-p abs))
        (let ((parent (file-name-directory (directory-file-name abs))))
          (and parent
               (file-directory-p parent)
               (file-writable-p parent))))))

(defun jolo-todo--worktree-parent (root)
  (let ((preferred (or jolo-todo-worktree-dir "/workspaces")))
    (if (jolo-todo--directory-writable-p preferred)
        (expand-file-name preferred)
      (expand-file-name "worktrees" root))))

(defun jolo-todo--git-run (root &rest args)
  (with-temp-buffer
    (let ((default-directory root))
      (cons (apply #'process-file "git" nil (current-buffer) nil args)
            (string-trim-right (buffer-string))))))

(defun jolo-todo--branch-exists-p (root branch)
  (eq 0 (car (jolo-todo--git-run root "rev-parse" "--verify" "--quiet"
                                 (format "refs/heads/%s" branch)))))

(defun jolo-todo--branch-worktree (root branch)
  (let* ((result (jolo-todo--git-run root "worktree" "list" "--porcelain"))
         (status (car result))
         (output (cdr result))
         (current-worktree nil)
         (match nil))
    (when (eq 0 status)
      (dolist (line (split-string output "\n" t))
        (cond
         ((string-prefix-p "worktree " line)
          (setq current-worktree (string-remove-prefix "worktree " line)))
         ((and current-worktree
               (string= line (format "branch refs/heads/%s" branch)))
          (setq match current-worktree)))))
    match))

(defun jolo-todo--next-worktree-identity (root heading)
  (let* ((slug (jolo-todo--slugify heading))
         (repo (file-name-nondirectory (directory-file-name root)))
         (parent (jolo-todo--worktree-parent root))
         (index 0)
         branch
         worktree)
    (while
        (progn
          (setq branch (if (zerop index)
                           (format "feat/%s" slug)
                         (format "feat/%s-%d" slug index)))
          (setq worktree
                (expand-file-name
                 (if (zerop index)
                     (format "%s-%s" repo slug)
                   (format "%s-%s-%d" repo slug index))
                 parent))
          (setq index (1+ index))
          (or (jolo-todo--branch-exists-p root branch)
              (file-exists-p worktree))))
    (cons branch worktree)))

(defun jolo-todo--ensure-id ()
  (unless (org-entry-get nil "ID")
    (org-entry-put nil "ID" (org-id-new))))

(defun jolo-todo--ensure-session-id ()
  (unless (org-entry-get nil "SESSION_ID")
    (org-entry-put nil "SESSION_ID" (jolo-todo--new-session-id))))

(defun jolo-todo--ensure-worktree ()
  (let* ((root (jolo-todo--repo-root (buffer-file-name)))
         (heading (org-get-heading t t t t))
         (branch (org-entry-get nil "BRANCH"))
         (worktree (org-entry-get nil "WORKTREE")))
    (ignore-errors (jolo-todo--git-run root "worktree" "prune"))
    (unless (and branch worktree)
      (pcase-let ((`(,new-branch . ,new-worktree)
                   (jolo-todo--next-worktree-identity root heading)))
        (unless branch
          (setq branch new-branch))
        (unless worktree
          (setq worktree new-worktree))))
    (let ((existing-worktree (and branch (jolo-todo--branch-worktree root branch))))
      (when existing-worktree
        (setq worktree existing-worktree)))
    (unless (file-directory-p worktree)
      (make-directory (file-name-directory worktree) t)
      (let* ((args (if (jolo-todo--branch-exists-p root branch)
                       (list "worktree" "add" worktree branch)
                     (list "worktree" "add" "-b" branch worktree)))
             (result (apply #'jolo-todo--git-run root args)))
        (unless (eq 0 (car result))
          (error "worktree create failed: %s" (cdr result)))))
    (org-entry-put nil "BRANCH" branch)
    (org-entry-put nil "WORKTREE" worktree)))

(defun jolo-todo--current-heading-marker ()
  (save-excursion
    (org-back-to-heading t)
    (cons (current-buffer) (point))))

(defun jolo-todo--clocked-heading-marker ()
  (when (and (boundp 'org-clock-marker)
             (marker-buffer org-clock-marker))
    (with-current-buffer (marker-buffer org-clock-marker)
      (save-excursion
        (goto-char (marker-position org-clock-marker))
        (org-back-to-heading t)
        (cons (current-buffer) (point))))))

(defun jolo-todo--clocking-current-heading-p ()
  (let ((clocked (jolo-todo--clocked-heading-marker))
        (current (jolo-todo--current-heading-marker)))
    (and clocked
         (eq (car clocked) (car current))
         (= (cdr clocked) (cdr current)))))

(defun jolo-todo--clock-in-current-heading ()
  (unless (jolo-todo--clocking-current-heading-p)
    (when (org-clocking-p)
      (ignore-errors (org-clock-out nil t)))
    (ignore-errors (org-clock-in))))

(defun jolo-todo--clock-out-current-heading ()
  (when (jolo-todo--clocking-current-heading-p)
    (ignore-errors (org-clock-out nil t))))

(defun jolo-todo--goto-by-property (property value)
  (goto-char (point-min))
  (catch 'found
    (while (re-search-forward org-heading-regexp nil t)
      (org-back-to-heading t)
      (when (string= (or (org-entry-get nil property) "") value)
        (throw 'found (point)))
      (outline-next-heading))
    nil))

(defun jolo-todo--goto-by-headline (headline)
  (goto-char (point-min))
  (let (matches)
    (while (re-search-forward org-heading-regexp nil t)
      (org-back-to-heading t)
      (when (string= (org-get-heading t t t t) headline)
        (push (point) matches))
      (outline-next-heading))
    (cond
     ((null matches) nil)
     ((cdr matches)
      (error "headline is ambiguous (%s). Use ID or SESSION_ID" headline))
     (t
      (goto-char (car matches))
      (car matches)))))

(defun jolo-todo-resume-by-session-id (session-id)
  "Jump to SESSION-ID in docs/TODO.org."
  (interactive (list (read-string "Session ID: ")))
  (let ((buffer (find-file-noselect (jolo-todo--todo-file))))
    (with-current-buffer buffer
      (org-with-wide-buffer
       (unless (jolo-todo--goto-by-property "SESSION_ID" session-id)
         (user-error "No task with SESSION_ID=%s" session-id))
       (org-show-entry)
       (org-reveal)))
    (switch-to-buffer buffer)))

(defun jolo-todo-agent-transition (selector-kind selector state)
  "Transition a task in docs/TODO.org.
SELECTOR-KIND is one of \"id\", \"session\", or \"headline\".
SELECTOR is the selector value.
STATE is one of TODO, NEXT, INPROGRESS, BLOCKED, DONE."
  (let ((allowed '("TODO" "NEXT" "INPROGRESS" "BLOCKED" "DONE"))
        (kind (if (symbolp selector-kind)
                  (symbol-name selector-kind)
                selector-kind)))
    (unless (member state allowed)
      (error "invalid state: %s" state))
    (with-current-buffer (find-file-noselect (jolo-todo--todo-file))
      (org-with-wide-buffer
       (jolo-todo--ensure-keywords)
       (let ((point (pcase kind
                      ("id" (jolo-todo--goto-by-property "ID" selector))
                      ("session" (jolo-todo--goto-by-property "SESSION_ID" selector))
                      ("headline" (jolo-todo--goto-by-headline selector))
                      (_ (error "invalid selector kind: %s" kind)))))
         (unless point
           (error "task not found (%s=%s)" kind selector))
         (goto-char point)
         (let ((heading (org-get-heading t t t t))
               (old-state (org-get-todo-state)))
           (org-todo state)
           (let ((org-last-state old-state)
                 (org-state state))
             (jolo-todo--after-state-change))
           (save-buffer)
           (format "%s -> %s (%s=%s)" heading state kind selector)))))))

(defun jolo-todo--after-state-change ()
  (when (and (boundp 'org-state)
             (stringp org-state)
             (jolo-todo--target-buffer-p))
    (save-excursion
      (org-back-to-heading t)
      (when (and (boundp 'org-last-state)
                 (string= org-last-state "INPROGRESS")
                 (not (string= org-state "INPROGRESS")))
        (jolo-todo--clock-out-current-heading))
      (pcase org-state
        ("INPROGRESS"
         (jolo-todo--ensure-id)
         (jolo-todo--ensure-session-id)
         (condition-case err
             (jolo-todo--ensure-worktree)
           (error
            (message "jolo-todo worktree: %s" (error-message-string err))))
         (jolo-todo--clock-in-current-heading))
        ((or "BLOCKED" "DONE")
         (jolo-todo--clock-out-current-heading))))))

(defun jolo-todo-enable ()
  "Enable docs/TODO.org workflow hooks."
  (interactive)
  (add-hook 'org-mode-hook #'jolo-todo--ensure-keywords)
  (add-hook 'org-after-todo-state-change-hook #'jolo-todo--after-state-change))

(defun jolo-todo-disable ()
  "Disable docs/TODO.org workflow hooks."
  (interactive)
  (remove-hook 'org-mode-hook #'jolo-todo--ensure-keywords)
  (remove-hook 'org-after-todo-state-change-hook #'jolo-todo--after-state-change))

(provide 'jolo-todo)
