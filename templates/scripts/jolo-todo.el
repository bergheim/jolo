;;; jolo-todo.el --- control-plane TODO automation -*- lexical-binding: t; -*-

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

(defcustom jolo-todo-control-file nil
  "Absolute path to the control docs/TODO.org.
Nil means auto-detect main worktree's docs/TODO.org."
  :type '(choice (const :tag "Auto-detect" nil) file))

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

(defun jolo-todo--git-run (root &rest args)
  (with-temp-buffer
    (let ((default-directory root))
      (cons (apply #'process-file "git" nil (current-buffer) nil args)
            (string-trim-right (buffer-string))))))

(defun jolo-todo--worktree-entries (root)
  (let* ((result (jolo-todo--git-run root "worktree" "list" "--porcelain"))
         (status (car result))
         (output (cdr result))
         (entries nil)
         (entry nil))
    (when (eq 0 status)
      (dolist (line (append (split-string output "\n") (list "")))
        (cond
         ((string-empty-p line)
          (when entry
            (push entry entries)
            (setq entry nil)))
         ((string-prefix-p "worktree " line)
          (setq entry (list :path (string-remove-prefix "worktree " line))))
         ((string-prefix-p "branch " line)
          (setq entry (plist-put entry :branch (string-remove-prefix "branch " line)))))))
    (nreverse entries)))

(defun jolo-todo--main-worktree-root (root)
  (let ((main-root nil))
    (dolist (entry (jolo-todo--worktree-entries root))
      (when (string= (or (plist-get entry :branch) "") "refs/heads/main")
        (setq main-root (plist-get entry :path))))
    main-root))

(defun jolo-todo--control-root (&optional path)
  (let* ((root (jolo-todo--repo-root path))
         (main-root (jolo-todo--main-worktree-root root)))
    (expand-file-name (or main-root root))))

(defun jolo-todo--todo-file (&optional path)
  (if jolo-todo-control-file
      (expand-file-name jolo-todo-control-file)
    (let* ((root (jolo-todo--repo-root path))
           (control-root (jolo-todo--control-root path))
           (control (expand-file-name "docs/TODO.org" control-root))
           (fallback (expand-file-name "docs/TODO.org" root)))
      (if (or (file-exists-p control)
              (not (file-exists-p fallback)))
          control
        fallback))))

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

(defun jolo-todo--branch-exists-p (root branch)
  (eq 0 (car (jolo-todo--git-run root "rev-parse" "--verify" "--quiet"
                                 (format "refs/heads/%s" branch)))))

(defun jolo-todo--branch-worktree (root branch)
  (let ((match nil)
        (needle (format "refs/heads/%s" branch)))
    (dolist (entry (jolo-todo--worktree-entries root))
      (when (string= (or (plist-get entry :branch) "") needle)
        (setq match (plist-get entry :path))))
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
  (let* ((control-file (jolo-todo--todo-file (buffer-file-name)))
         (root (jolo-todo--repo-root control-file))
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

(defun jolo-todo--find-by-selector (kind selector)
  (pcase kind
    ("id" (jolo-todo--goto-by-property "ID" selector))
    ("session" (jolo-todo--goto-by-property "SESSION_ID" selector))
    ("headline" (jolo-todo--goto-by-headline selector))
    (_ (error "invalid selector kind: %s" kind))))

(defun jolo-todo--append-note-line (note)
  (org-back-to-heading t)
  (org-end-of-meta-data t)
  (beginning-of-line)
  (insert (format "- [%s] %s\n"
                  (format-time-string "%Y-%m-%d %a %H:%M")
                  note)))

(defun jolo-todo-open-control ()
  "Open the control docs/TODO.org buffer."
  (interactive)
  (switch-to-buffer (find-file-noselect (jolo-todo--todo-file default-directory))))

(defun jolo-todo-resume-by-session-id (session-id)
  "Jump to SESSION-ID in the control docs/TODO.org."
  (interactive (list (read-string "Session ID: ")))
  (let ((buffer (find-file-noselect (jolo-todo--todo-file default-directory))))
    (with-current-buffer buffer
      (org-with-wide-buffer
       (unless (jolo-todo--goto-by-property "SESSION_ID" session-id)
         (user-error "No task with SESSION_ID=%s" session-id))
       (org-show-entry)
       (org-reveal)))
    (switch-to-buffer buffer)))

(defun jolo-todo-agent-transition (selector-kind selector state)
  "Transition a task in control docs/TODO.org.
SELECTOR-KIND is one of "id", "session", or "headline".
SELECTOR is the selector value.
STATE is one of TODO, NEXT, INPROGRESS, BLOCKED, DONE."
  (let ((allowed '("TODO" "NEXT" "INPROGRESS" "BLOCKED" "DONE"))
        (kind (if (symbolp selector-kind)
                  (symbol-name selector-kind)
                selector-kind)))
    (unless (member state allowed)
      (error "invalid state: %s" state))
    (with-current-buffer (find-file-noselect (jolo-todo--todo-file default-directory))
      (org-with-wide-buffer
       (jolo-todo--ensure-keywords)
       (let ((point (jolo-todo--find-by-selector kind selector)))
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

(defun jolo-todo-agent-note (selector-kind selector note)
  "Append NOTE under a task in control docs/TODO.org."
  (let ((kind (if (symbolp selector-kind)
                  (symbol-name selector-kind)
                selector-kind)))
    (with-current-buffer (find-file-noselect (jolo-todo--todo-file default-directory))
      (org-with-wide-buffer
       (let ((point (jolo-todo--find-by-selector kind selector)))
         (unless point
           (error "task not found (%s=%s)" kind selector))
         (goto-char point)
         (let ((heading (org-get-heading t t t t)))
           (jolo-todo--append-note-line note)
           (save-buffer)
           (format "%s note added (%s=%s)" heading kind selector)))))))

(defun jolo-todo--current-heading-id ()
  (unless (jolo-todo--target-buffer-p)
    (user-error "Open control docs/TODO.org (M-x jolo-todo-open-control)"))
  (org-back-to-heading t)
  (or (org-entry-get nil "ID")
      (progn
        (jolo-todo--ensure-id)
        (save-buffer)
        (org-entry-get nil "ID"))))

(defun jolo-todo--transition-current (state)
  (jolo-todo-agent-transition "id" (jolo-todo--current-heading-id) state)
  (revert-buffer :ignore-auto :noconfirm))

(defun jolo-todo-next ()
  "Set current control task to NEXT."
  (interactive)
  (jolo-todo--transition-current "NEXT"))

(defun jolo-todo-start ()
  "Set current control task to INPROGRESS."
  (interactive)
  (jolo-todo--transition-current "INPROGRESS"))

(defun jolo-todo-block ()
  "Set current control task to BLOCKED."
  (interactive)
  (jolo-todo--transition-current "BLOCKED"))

(defun jolo-todo-done ()
  "Set current control task to DONE."
  (interactive)
  (jolo-todo--transition-current "DONE"))

(defun jolo-todo-note (note)
  "Add NOTE under current control task."
  (interactive "sNote: ")
  (jolo-todo-agent-note "id" (jolo-todo--current-heading-id) note)
  (revert-buffer :ignore-auto :noconfirm))

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
  "Enable control TODO workflow hooks and keybindings."
  (interactive)
  (add-hook 'org-mode-hook #'jolo-todo--ensure-keywords)
  (add-hook 'org-after-todo-state-change-hook #'jolo-todo--after-state-change)
  (define-key org-mode-map (kbd "C-c j o") #'jolo-todo-open-control)
  (define-key org-mode-map (kbd "C-c j n") #'jolo-todo-next)
  (define-key org-mode-map (kbd "C-c j s") #'jolo-todo-start)
  (define-key org-mode-map (kbd "C-c j b") #'jolo-todo-block)
  (define-key org-mode-map (kbd "C-c j d") #'jolo-todo-done)
  (define-key org-mode-map (kbd "C-c j m") #'jolo-todo-note)
  (define-key org-mode-map (kbd "C-c j r") #'jolo-todo-resume-by-session-id))

(defun jolo-todo-disable ()
  "Disable control TODO workflow hooks and keybindings."
  (interactive)
  (remove-hook 'org-mode-hook #'jolo-todo--ensure-keywords)
  (remove-hook 'org-after-todo-state-change-hook #'jolo-todo--after-state-change)
  (define-key org-mode-map (kbd "C-c j o") nil)
  (define-key org-mode-map (kbd "C-c j n") nil)
  (define-key org-mode-map (kbd "C-c j s") nil)
  (define-key org-mode-map (kbd "C-c j b") nil)
  (define-key org-mode-map (kbd "C-c j d") nil)
  (define-key org-mode-map (kbd "C-c j m") nil)
  (define-key org-mode-map (kbd "C-c j r") nil))

(provide 'jolo-todo)
