-- Records the files a Neovim session wrote, with the user's summary, to the logbook journal.
-- Set vim.g.auto_logbook_disable = true to turn it off.

local PROMPT = "Enter session summary: "
-- input() returns this on Escape. A typed summary cannot hold it, since Escape cancels.
local CANCELLED = "\27"

local started = os.time()
local written = {}
local group = vim.api.nvim_create_augroup("auto_logbook", { clear = true })

local function enabled()
  return not vim.g.auto_logbook_disable and vim.fn.executable("logbook") == 1
end

local function has_ui()
  return #vim.api.nvim_list_uis() > 0
end

-- Returns the summary, "" for none, or nil when the user cancelled.
local function ask_summary()
  local ok, text = pcall(vim.fn.input, { prompt = PROMPT, cancelreturn = CANCELLED })

  if not ok or text == CANCELLED then
    return nil
  end

  return vim.trim(text)
end

local function capture_command(summary)
  local files = vim.tbl_keys(written)

  table.sort(files)

  local command = {
    "logbook", "capture", "nvim", "--cwd", vim.fn.getcwd(), "--started", tostring(started),
  }

  if summary ~= "" then
    vim.list_extend(command, { "--summary", summary })
  end

  table.insert(command, "--")
  vim.list_extend(command, files)

  return command
end

local function reset()
  written = {}
  started = os.time()
end

vim.api.nvim_create_autocmd("BufWritePost", {
  group = group,
  callback = function(event)
    local name = vim.api.nvim_buf_get_name(event.buf)

    if name ~= "" and vim.bo[event.buf].buftype == "" then
      written[vim.fn.fnamemodify(name, ":p")] = true
    end
  end,
})

vim.api.nvim_create_autocmd("VimLeavePre", {
  group = group,
  callback = function()
    if not enabled() or vim.tbl_isempty(written) then
      return
    end

    local summary = ""

    if has_ui() then
      summary = ask_summary()
    end

    if summary == nil then
      return
    end

    vim.fn.system(capture_command(summary))
  end,
})

vim.api.nvim_create_user_command("Logbook", function(options)
  if not enabled() then
    vim.notify("logbook is not on PATH, or auto_logbook_disable is set", vim.log.levels.WARN)

    return
  end

  local summary = vim.trim(options.args)

  if summary == "" then
    summary = ask_summary()
  end

  if summary == nil then
    return
  end

  if summary == "" and vim.tbl_isempty(written) then
    vim.notify("Nothing to log: no summary and no files written", vim.log.levels.WARN)

    return
  end

  local command = capture_command(summary)

  reset()
  vim.system(command, { text = true }, function(result)
    if result.code ~= 0 then
      vim.schedule(function()
        vim.notify("logbook failed: " .. (result.stderr or ""), vim.log.levels.ERROR)
      end)
    end
  end)
end, { nargs = "*", desc = "Add a logbook entry for the files written since the last one" })

vim.keymap.set("n", "<Leader>nl", "<cmd>Logbook<cr>", { desc = "Logbook: add a session entry" })
